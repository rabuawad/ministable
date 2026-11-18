[Feynman: modules/cdp/cdp.vy] The module records collateral, debt, interest, redemptions, and liquidations; its arithmetic assumes debt shares and token amounts remain consistent after rounding.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens; its accounting assumes the token debits and credits the amounts that the module records.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin; its payout routes assume the shared accounting returns the correct amount.

[Feynman: modules/tokens/erc20.vy] The module records stablecoin balances and allowances; its share-accounting caller determines how much stablecoin enters and leaves circulation.

[Socratic: modules/cdp/cdp.vy:_repay — why?] Why does a partial repayment proceed when the amount removes zero shares?

[Inversion: _liquidate] An attacker can select a one-unit repayment, choose a position near the minimum ratio, or wait until the index exceeds one.

[Inversion: _push] A token can charge the sender, charge the recipient, or reject a zero transfer.

[Inversion: _buy_surplus] A buyer can submit before an oracle update, receive fewer tokens after an update, or leave a surplus smaller than one collateral unit.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: Borrower → withdraw → accounting removes the requested collateral → a sender-fee token debits extra collateral → other users lose backing.
proof: If the contract holds 200 tokens for two users and a transfer of 100 debits 101, the first withdrawal leaves 99 tokens against the second user’s 100-token claim; `_push` checks only the transfer return value.
description: A borrower withdraws with a sender-fee token, so the token takes collateral that belongs to other users.
fix: The module should reject an outflow unless its balance falls by exactly the accounted amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: Redeemer → redeem → gross payout passes `min_paid` → a recipient-fee token reduces the received amount.
proof: For `paid = 100` and `min_paid = 100`, `_redeem` accepts the payout; a 1% recipient fee makes the redeemer receive 99 while the function returns 100.
description: A redeemer accepts a minimum payout, but a token transfer fee gives the redeemer less than that minimum.
fix: The module should check the recipient’s balance increase against `min_paid`.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: zero-share-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | zero-share-liquidation
code_smells: A partial repayment removes `amount * 10**18 // rate_index` shares, and liquidation can seize collateral when that result is zero.
unverified: A material attack requires an index, collateral price, and transaction cost that make repeated zero-share repayments economically significant.
description: A liquidator can remove collateral while a small repayment removes no debt shares.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: zero-share-redemption | group_key: modules/cdp/cdp.vy | _redeem | zero-share-redemption
code_smells: A redemption pays collateral after `_repay` removes `amount * 10**18 // rate_index` shares, which can equal zero.
unverified: A material attack requires a collateral price and index that make repeated payouts significant after token costs and transaction costs.
description: A redeemer can remove collateral while a small repayment removes no debt shares.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The branch below 110% collateralization requires `max_repay >= repay` and clears all debt shares in one call.
unverified: The available stablecoin liquidity and liquidation funding paths must support a conclusion about a specific position.
description: A liquidator needs the full required repayment in one call to close a deeply undercollateralized position.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The solvent branch calculates `seized = repay * LIQUIDATION_PENALTY // p`, which can equal zero.
unverified: A material loss requires collateral units and a price that make the minimum useful liquidation payout round to zero.
description: A liquidator can repay debt and receive zero collateral when the payout rounds down.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: discarded-interest-fractions | group_key: modules/cdp/cdp.vy | _accrue | discarded-interest-fractions
code_smells: Each update floors `total_debt_shares * (index - rate_index) // 10**18` and retains no fractional remainder.
unverified: A material supply shortfall requires a reachable principal and update frequency that produce significant cumulative discarded interest.
description: A caller can trigger frequent updates that discard fractional interest owed to the surplus.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: caller-driven-compounding | group_key: modules/cdp/cdp.vy | _accrue | caller-driven-compounding
code_smells: Each update applies elapsed interest to the current index, and an external caller can trigger an update with `mint(0)`.
unverified: The intended interest model must specify whether callers may choose the compounding frequency.
description: A caller can increase borrower debt by choosing more frequent interest updates.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: `burn` accepts an exact amount, while `_accrue` can increase debt before `_repay` compares that amount with the debt.
unverified: The available transaction infrastructure must show whether a borrower can reliably submit the exact debt at execution time.
description: A borrower can retain debt after interest changes between the debt quote and repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: The purchase calculates `bought` from the current oracle price and accepts no minimum output.
unverified: A material loss requires an oracle update between submission and execution that reduces the purchase output.
description: A buyer can receive fewer stablecoins than expected after the oracle price changes.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: coarse-surplus-unbuyable | group_key: modules/cdp/cdp.vy | _buy_surplus | coarse-surplus-unbuyable
code_smells: The purchase requires `bought <= erc20.balanceOf[self]`, but collateral payments use whole base units.
unverified: The collateral price and surplus balance must leave a residue smaller than the stablecoin output for one collateral base unit.
description: A buyer cannot purchase a surplus residue smaller than the output for one collateral base unit.

LEAD | contract: modules/cdp/cdp.vy | function: mint | bug_class: no-minimum-debt | group_key: modules/cdp/cdp.vy | mint | no-minimum-debt
code_smells: `mint` sets no minimum position debt, and liquidation rewards scale with the debt repaid.
unverified: A material accumulation requires positions whose liquidation rewards remain below execution costs.
description: Borrowers can create positions whose liquidation rewards do not cover a liquidator’s costs.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The module calls `_push` even when the calculated `seized` amount equals zero.
unverified: The deployed collateral token must reject zero transfers, and a reachable liquidation must calculate zero seized collateral.
description: A collateral token that rejects zero transfers can block a liquidation with a zero payout.
