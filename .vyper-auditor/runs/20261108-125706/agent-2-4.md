[Feynman: modules/cdp/cdp.vy] The module records collateral and debt, then tells a wrapper how much collateral to send; the module binding supplies the stablecoin state.

[Feynman: modules/cdp/cdp_erc20.vy] The wrapper measures deposits and sends collateral after accounting changes; the token defines the actual balance changes.

[Feynman: modules/cdp/cdp_native.vy] The wrapper receives native coin and sends it after accounting changes; exported functions retain their defining module’s protection.

[Feynman: modules/tokens/erc20.vy] The module records stablecoin balances, allowances, and permits; its host binds and exports the module.

[Feynman: src/ministable.vy] The host binds the native collateral and stablecoin modules and treats plain native coin transfers as deposits; module exports define its external routes.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the wrapper assume the token reduces its balance by exactly the requested amount?

[Inversion: _push] A caller withdraws with a sender-fee token; a redeemer receives a recipient-fee token; a liquidator receives zero units from a token that rejects zero transfers.

[Inversion: _liquidate] A caller supplies a small `max_repay`; a price update places a position below 110%; a caller selects coarse collateral whose calculated payout rounds to zero.

[Inversion: _buy_surplus] A buyer submits before an oracle update; another buyer consumes the surplus first; a buyer pays one collateral base unit.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: Depositor → withdraw → `_withdraw` debits the requested collateral → `_push` transfers it and the token charges an additional sender fee → other depositors lose collateral.
input: The depositor withdraws 100 collateral tokens from a token that charges the sender an additional 10%.
assumption: The wrapper assumes its token balance falls by exactly `amount`.
proof: Two users each deposit 100 tokens, so the wrapper holds 200 and records 200; one withdraws 100, and `_push` causes a 110-token debit while accounting falls by only 100, leaving 90 tokens for the other user’s 100-token claim.
description: A depositor can withdraw collateral through a sender-fee token and consume collateral owed to other users.
fix: The wrapper should verify that its balance falls by exactly `amount` and revert if it does not.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: Redeemer → redeem → `_redeem` checks the gross payout → `_push` transfers collateral with a recipient fee → the redeemer receives less than `min_paid`.
input: The redeemer sets `min_paid` to 99.5 collateral tokens for a 100 mUSD redemption at a 1 USD price and 0.5% redemption fee.
assumption: The wrapper assumes the recipient receives the gross amount passed to `_push`.
proof: `_redeem` computes and accepts `paid = 99.5` tokens, but a 10% recipient fee leaves the caller 89.55 tokens; the function returns 99.5 and does not check the recipient’s balance.
description: A redeemer can receive fewer collateral tokens than `min_paid` when the token charges a recipient fee.
fix: The wrapper should check the recipient’s actual balance increase against `min_paid`.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The branch below 110% collateral requires `max_repay >= repay` and clears all debt shares in one call.
unverified: The availability of enough mUSD in one liquidator balance for a particular large position remains unverified.
description: A liquidator needs the full repayment in one balance before this branch clears a position.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The function floors `repay * LIQUIDATION_PENALTY // p` to collateral base units.
unverified: A deployed collateral and oracle price that make a material liquidation payout round to zero remain unverified.
description: A liquidator can receive zero collateral when the calculated payout is less than one collateral base unit.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The function passes `seized` to `_push` even when `seized` is zero.
unverified: A supported deployed collateral token that rejects zero transfers and a reachable zero-payout position remain unverified.
description: A collateral token that rejects zero transfers can block a liquidation with zero payout.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: The function calculates `bought` from the current oracle price and accepts no minimum output from the buyer.
unverified: A buyer’s pending transaction and an adverse oracle update before its execution remain unverified.
description: An oracle update can reduce the mUSD that a buyer receives for collateral.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The caller supplies a fixed `amount`, and `_accrue` updates the debt before `_repay` checks that amount.
unverified: The transaction timestamp and debt change between a borrower’s quote and execution remain unverified.
description: A borrower can retain debt after an interest update changes the amount needed to close the position.
