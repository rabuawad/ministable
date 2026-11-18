[Feynman: modules/cdp/cdp.vy] The module records collateral and debt, prices positions, and calculates payouts; module exports determine which host entry points expose its state.

[Feynman: modules/cdp/cdp_erc20.vy] The wrapper receives and sends collateral tokens; it assumes an outgoing transfer reduces its balance by exactly the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The wrapper receives native coin and sends calculated payouts; it assumes each receiver accepts the call.

[Feynman: modules/tokens/erc20.vy] The module records stablecoin balances, allowances, and signatures; its host must bind and export the intended module instance.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the wrapper measure tokens received but not tokens removed from its balance?

[Inversion: _push] An attacker withdraws with a sender-fee token; a redeemer selects a recipient-fee token; a liquidator requests a payout that rounds to zero.

[Inversion: _accrue] A caller invokes `mint(0)` repeatedly; a borrower repays near an accrual boundary; a caller triggers settlement before a surplus purchase.

[Inversion: _price] An oracle reports an older market price; a feed reaches its configured floor; a feed stops reporting entirely.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
boundary: ERC-20 collateral wrapper.
assumption: The wrapper assumes `transfer(to, amount)` reduces its token balance by exactly `amount`.
path: Borrower → `withdraw` → `_push` → sender fee reduces the wrapper balance beyond the recorded collateral debit → other depositors lose collateral.
proof: With a token that charges the sender 1%, two users each deposit 100 tokens. A withdrawal of 100 debits the first user's recorded collateral by 100, but `_push` sends 100 and the token removes 101. The wrapper retains 99 tokens against the second user's 100-token claim. The same helper serves `liquidate`, `redeem`, and `cover_bad_debt`.
description: A borrower can withdraw with a sender-fee token and consume collateral that belongs to other users.
fix: The wrapper must reject an outgoing transfer unless its balance decreases by exactly `amount`.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
boundary: ERC-20 collateral wrapper.
assumption: The redeemer assumes `min_paid` protects the amount received after token transfer.
path: Redeemer → `redeem` → `_redeem` checks the nominal payout → `_push` sends a fee-charging token → redeemer receives less than `min_paid`.
proof: `_redeem` checks `paid >= min_paid` before `_push(msg.sender, paid)`. For `paid = min_paid = 100` and a 1% recipient fee, the call succeeds while the redeemer receives 99.
description: A redeemer can receive less collateral than `min_paid` when the token charges a transfer fee.
fix: The wrapper must check the recipient's balance increase against `min_paid`.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The underwater branch requires `max_repay >= repay` and clears the position in one call.
unverified: A position must become large enough that no liquidator can obtain the required mUSD or finance the repayment.
description: A large underwater position can require one liquidator to provide its entire repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The function calculates `seized = repay * LIQUIDATION_PENALTY // p` without requiring a positive result.
unverified: A supported collateral price and position must make the required repayment economically material while `seized` equals zero.
description: A liquidator can receive zero collateral when the payout rounds down.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The wrapper calls `_push` even when `seized` is zero.
unverified: A supported token must reject zero transfers, and a reachable liquidation must calculate zero `seized`.
description: A token that rejects zero transfers can make a liquidator's call revert.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: zero-fee-oracle-swap | group_key: modules/cdp/cdp.vy | _buy_surplus | zero-fee-oracle-swap
code_smells: The purchase uses the latest accepted oracle answer and a fixed 0.5% fee.
unverified: A supported feed must remain within `ORACLE_TIMEOUT` while its answer exceeds the executable market price by more than the fee and transaction costs.
description: A buyer can receive excess mUSD if the accepted oracle price exceeds the market price.

LEAD | contract: modules/cdp/cdp.vy | function: _cover_bad_debt | bug_class: zero-fee-oracle-swap | group_key: modules/cdp/cdp.vy | _cover_bad_debt | zero-fee-oracle-swap
code_smells: The payout uses the latest accepted oracle answer and a fixed 0.5% fee.
unverified: A supported feed must remain within `ORACLE_TIMEOUT` while its answer falls below the executable market price by more than the fee and transaction costs.
description: A caller can receive excess reserve collateral if the accepted oracle price falls below the market price.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: redemption-oracle-lag-extraction | group_key: modules/cdp/cdp.vy | _redeem | redemption-oracle-lag-extraction
code_smells: The redemption payout uses the latest accepted oracle answer and a fee based on the position ratio.
unverified: A supported feed must lag the executable market price by more than the applicable redemption fee and transaction costs.
description: A redeemer can receive excess borrower collateral if the accepted oracle price falls below the market price.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: chainlink-min-answer-clamp | group_key: modules/cdp/cdp.vy | _price | chainlink-min-answer-clamp
code_smells: The function accepts every positive answer that meets `ORACLE_TIMEOUT`.
unverified: A deployed feed must clamp answers at a floor above the executable market price.
description: A borrower can retain excess debt if the oracle floor exceeds the market price.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: immutable-oracle-no-fallback | group_key: modules/cdp/cdp.vy | _price | immutable-oracle-no-fallback
code_smells: `ORACLE` is immutable, and every price-dependent path requires a valid answer from it.
unverified: The deployed feed must stop or retire without a compatible replacement at the same address.
description: A retired oracle can block callers from using price-dependent functions.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock
code_smells: The function calls `_collat_ratio` after each collateral debit.
unverified: The configured oracle must fail or exceed `ORACLE_TIMEOUT` while a borrower retains debt.
description: An oracle outage can block a borrower from withdrawing collateral while debt remains.

LEAD | contract: modules/cdp/cdp.vy | function: mint | bug_class: no-minimum-debt | group_key: modules/cdp/cdp.vy | mint | no-minimum-debt
code_smells: The function accepts debt amounts without a minimum position size.
unverified: Gas costs and market conditions must exceed the available liquidation reward for a material set of positions.
description: A borrower can create a position whose liquidation reward does not cover a liquidator's costs.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The caller supplies an exact `amount`, while `_accrue` updates debt before `_repay`.
unverified: The configured fee and transaction timing must prevent a borrower from supplying a sufficient exact repayment.
description: A borrower can retain debt when interest increases after the borrower calculates the repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: caller-driven-compounding | group_key: modules/cdp/cdp.vy | _accrue | caller-driven-compounding
code_smells: Each call updates `rate_index`, and exported `mint(0)` can trigger an update.
unverified: The deployed stability fee, update frequency, and gas costs must make the extra interest material.
description: A caller can increase borrowers' interest by choosing more frequent accrual updates.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: discarded-interest-fractions | group_key: modules/cdp/cdp.vy | _accrue | discarded-interest-fractions
code_smells: Each update floors `total_debt_shares * (index - self.rate_index) // PRECISION`.
unverified: A reachable debt balance and update schedule must produce a material difference between debt growth and minted surplus.
description: A caller can reduce minted surplus through repeated accruals that discard fractional fees.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: The function calculates `bought` from the current oracle answer without a caller-supplied minimum.
unverified: A buyer must submit a transaction before an adverse oracle update and lack an external transaction-level output check.
description: A buyer can receive fewer mUSD than expected after an oracle update.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: stranded-reserve | group_key: modules/cdp/cdp.vy | _buy_surplus | stranded-reserve
code_smells: The purchase increases `reserve`, and `_cover_bad_debt` is the only shown path that reduces it.
unverified: The protocol must require another use or withdrawal of reserve collateral when no bad debt exists.
description: The protocol can retain reserve collateral when no bad debt exists.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: coarse-surplus-unbuyable | group_key: modules/cdp/cdp.vy | _buy_surplus | coarse-surplus-unbuyable
code_smells: The purchase requires `bought <= erc20.balanceOf[self]` and accepts collateral in whole base units.
unverified: The remaining surplus must be smaller than the output from one collateral base unit and matter to the protocol.
description: A buyer can be unable to purchase a surplus balance smaller than one collateral unit permits.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: token-pause-blocks-liquidation | group_key: modules/cdp/cdp_erc20.vy | liquidate | token-pause-blocks-liquidation
code_smells: The wrapper requires the collateral token transfer to succeed after liquidation accounting.
unverified: A supported collateral token must pause transfers while positions require liquidation.
description: A paused collateral token can block liquidators from closing positions.
