[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, liquidations, redemptions, and reserves; its wrappers must deliver the amounts that its accounting records.

[Feynman: modules/cdp/cdp_erc20.vy] The module measures tokens received and sends tokens owed; it assumes an outgoing transfer spends and delivers the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The module receives native coin and sends the amounts calculated by the CDP; its accounting assumes each successful call sends the requested value.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances, allowances, and signed approvals; its host must initialize and export the intended module instance.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the module measure the balance change on receipt but assume the balance change on payment?

[Inversion: _push] A caller can withdraw a sender-fee token, redeem a recipient-fee token, or liquidate while a token rejects zero transfers.

[Inversion: _liquidate] A liquidator can choose a small `max_repay`, face a position below 110%, or call after a price change.

[Inversion: _price] An oracle can return a price at its floor, stop updates, or report a price that differs from the market within the timeout.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: depositor → withdraw → `_withdraw` reduces the depositor’s credit → `_push` pays a sender-fee token → other depositors lose backing
proof: Two users each deposit 100 tokens, so the contract holds 200 and records 200. If the token charges the sender an extra 1% on transfer, the first user withdraws 100; `_withdraw` removes 100 from that user’s credit, but `_push` reduces the contract balance by 101. The remaining user has a 100-token claim against 99 tokens. The same `_push` serves liquidation, redemption, and bad-debt coverage.
description: A sender-fee token takes more collateral than the module removes from the caller’s account, so other depositors lose collateral.
fix: The module should reject outgoing transfers that reduce its balance by more than the accounted amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: redeemer → `redeem` → `_redeem` accepts nominal `paid` against `min_paid` → recipient-fee token reduces the received amount
proof: If `_redeem` calculates `paid = 100` and the caller sets `min_paid = 100`, the check passes. A token that deducts a 1% fee from the recipient delivers 99, while `redeem` returns 100 and the caller’s stablecoin remains burned.
description: A recipient-fee token gives the redeemer less collateral than `min_paid` while the redemption succeeds.
fix: The module should check the recipient’s actual balance increase against `min_paid`.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The function requires one liquidator to repay the full calculated amount when collateral value falls below 110% of debt.
unverified: The available stablecoin liquidity and transaction capacity must be insufficient for a particular position’s required repayment.
description: A large position can remain open if no liquidator can obtain its required repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The function floors `repay * LIQUIDATION_PENALTY // p` to collateral base units.
unverified: The collateral price, token precision, and position size must make the economically necessary payout less than one base unit.
description: A liquidator can receive zero collateral when the calculated payout is less than one base unit.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The function calls `_push` even when `_liquidate` returns zero collateral.
unverified: The configured collateral token must reject zero transfers, and a liquidation must reach a zero payout.
description: A token that rejects zero transfers can block a liquidation with a zero collateral payout.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: zero-fee-oracle-swap | group_key: modules/cdp/cdp.vy | _buy_surplus | zero-fee-oracle-swap
code_smells: The function values collateral at the oracle price and applies a fixed 0.5% fee.
unverified: The configured oracle must remain valid while its price exceeds the executable market price by more than the fee and trading costs.
description: A buyer can receive excess stablecoin if the oracle price exceeds the market price by more than the fee.

LEAD | contract: modules/cdp/cdp.vy | function: _cover_bad_debt | bug_class: zero-fee-oracle-swap | group_key: modules/cdp/cdp.vy | _cover_bad_debt | zero-fee-oracle-swap
code_smells: The function pays reserve collateral at the oracle price and applies a fixed 0.5% fee.
unverified: The configured oracle must remain valid while its price falls below the executable market price by more than the fee and trading costs.
description: A caller can receive excess reserve collateral if the oracle price falls below the market price by more than the fee.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: redemption-oracle-lag-extraction | group_key: modules/cdp/cdp.vy | _redeem | redemption-oracle-lag-extraction
code_smells: The function values borrower collateral at the oracle price and applies a fee based on the position ratio.
unverified: The configured oracle must remain valid while its price falls below the executable market price by more than the applicable fee and trading costs.
description: A redeemer can receive excess borrower collateral if the oracle price falls below the market price by more than the fee.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: chainlink-min-answer-clamp | group_key: modules/cdp/cdp.vy | _price | chainlink-min-answer-clamp
code_smells: The function accepts any positive answer within `ORACLE_TIMEOUT`, including an answer at an aggregator floor.
unverified: The deployed feed must have an active floor that exceeds the collateral’s market price.
description: A caller can use an oracle floor that exceeds the market price to obtain excess stablecoin against collateral.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: immutable-oracle-no-fallback | group_key: modules/cdp/cdp.vy | _price | immutable-oracle-no-fallback
code_smells: The function reads one immutable oracle and rejects answers older than `ORACLE_TIMEOUT`.
unverified: The configured feed must stop producing valid answers without a replacement path.
description: An oracle that stops updates can block price-dependent operations.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock
code_smells: The function checks `_collat_ratio` after it removes collateral, and that check reads the oracle when debt remains.
unverified: The oracle must fail or return an answer outside the accepted time window.
description: An oracle failure blocks a borrower from withdrawing collateral while the position retains debt.
