[Feynman: modules/cdp/cdp.vy] The module records collateral and debt, then calculates payments for liquidations, redemptions, and reserve trades. Its share conversion depends on Vyper integer division.

[Feynman: modules/cdp/cdp_erc20.vy] The module measures collateral received and sends collateral owed. Its transfer calls depend on the token’s implementation.

[Feynman: modules/cdp/cdp_native.vy] The module receives native coin and sends the amounts calculated by the CDP module. Its exported calls depend on module binding.

[Feynman: modules/tokens/erc20.vy] The module records token balances, allowances, and signatures. Its unchecked arithmetic depends on the supply and balance invariants.

[Socratic: modules/cdp/cdp.vy — _repay] Why may a partial repayment remove zero shares while liquidation still pays collateral?

[Inversion: _liquidate] An attacker can choose a small repayment, wait for the index to rise, or target a position just below the minimum ratio.

[Inversion: _push] A caller can use a token with a sender fee, use a token with a recipient fee, or request the final available collateral balance.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: borrower → withdraw → accounting deducts the requested amount → collateral token charges an extra sender fee → other borrowers lack collateral
proof: Two borrowers each deposit 100 units, so the contract holds 200 units. If a supported token charges the sender an additional 10% on transfer, the first borrower withdraws 100 units and the contract loses 110. The second borrower still has a claim for 100 units, but the contract holds only 90. `_push` checks the return value but does not check the contract’s balance decrease.
description: A borrower can withdraw collateral with a sender fee, so the contract uses collateral owed to other borrowers.
fix: The module should reject a transfer when its collateral balance decreases by more than the accounted amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: redeemer → redeem → `_redeem` checks gross `paid` against `min_paid` → `_push` transfers less after a recipient fee → redeemer receives less than the minimum
proof: If `_redeem` calculates `paid = 100` and the caller sets `min_paid = 100`, the check passes. A token that deducts a 10% fee from the recipient delivers 90 units, while `redeem` returns 100.
description: A redeemer can receive less collateral than `min_paid` when the collateral token charges a recipient fee.
fix: The module should check the recipient’s balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The function rounds `seized` down and accepts a positive repayment when `seized` is zero.
unverified: The economic impact depends on the collateral price, its decimals, and whether positions remain unliquidated until a larger price change.
description: A liquidator can receive zero collateral for a positive repayment, so a small shortfall may remain open.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: zero-share-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | zero-share-liquidation
code_smells: The function pays collateral after `_repay` rounds removed shares down to zero.
unverified: A material loss requires a reachable index, collateral price, and transaction cost that make repeated repayments with zero removed shares economical.
description: A liquidator can receive collateral while a small repayment removes no debt shares.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: discarded-interest-fractions | group_key: modules/cdp/cdp.vy | _accrue | discarded-interest-fractions
code_smells: Each index update floors the fee before it mints surplus, and the function does not retain the fraction.
unverified: The maximum cumulative loss must be compared with reachable update frequency and transaction costs.
description: A caller can trigger frequent updates that discard fractional interest owed to the surplus.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The branch below 110% requires `max_repay >= repay` and clears all debt shares in one call.
unverified: The impact depends on the liquidity available to callers for the affected position.
description: A liquidator must supply the full repayment for a position below 110%, so a large position may remain open.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: The function calculates `bought` from the current oracle price and accepts no minimum output.
unverified: A harmful execution requires a price update between the buyer’s quote and transaction.
description: A buyer can receive fewer mUSD than expected after an oracle price update.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: redemption-oracle-lag-extraction | group_key: modules/cdp/cdp.vy | _redeem | redemption-oracle-lag-extraction
code_smells: The function calculates collateral paid from the latest accepted oracle answer and a fee capped at 5%.
unverified: A loss requires an accepted oracle price that differs from the market price by more than the applicable fee and costs.
description: A redeemer can take excess borrower collateral if an accepted oracle price remains below the market price.
