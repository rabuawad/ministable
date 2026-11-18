[Feynman: modules/cdp/cdp.vy] The module records collateral and debt, charges interest, and calculates collateral payouts. Its share arithmetic assumes that each accounting change represents the intended token amount.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens. Its accounting assumes that a successful token transfer has the expected balance effects.

[Feynman: modules/cdp/cdp_native.vy] The module receives native coin and sends the collateral calculated by the CDP module. Its accounting assumes that each native transfer either succeeds or reverts.

[Feynman: modules/tokens/erc20.vy] The module records stablecoin balances, allowances, and signed approvals. Its signature checks depend on the imported recovery and domain modules.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the module measure collateral received but trust the amount delivered to the recipient?

[Inversion: _push] A caller withdraws with a recipient-fee token; a redeemer sets `min_paid`; a liquidator receives a token that charges the sender an extra fee.

[Inversion: _buy_surplus] A buyer submits before an oracle update; a caller changes the surplus through settlement; a buyer supplies collateral after the price falls.

[Inversion: _liquidate] A liquidator supplies less than the required repayment; a borrower falls below 100% collateralization; a liquidator holds only part of the required stablecoin.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: redeemer → `redeem` → `cdp._redeem` checks nominal `paid` → `_push` transfers collateral → recipient receives less than `min_paid`
pair_or_branch: `_pull` / `_push`; `redeem` accounting / recipient balance
asymmetry: `_pull` measures the contract balance change, while `_push` checks only the token’s boolean return and `redeem` checks only nominal `paid`.
proof: If `paid = min_paid = 100` and the collateral token deducts a 10% fee from the recipient’s transfer, `_redeem` accepts 100 and `_push` succeeds, but the redeemer receives 90. The module documents support for tokens that charge transfer fees.
description: The module checks the nominal redemption payout, so a recipient of a fee-charging token can receive less than `min_paid`.
fix: Measure the recipient’s balance change and enforce `min_paid` against the amount received, or reject collateral tokens that charge transfer fees.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: sender-fee-collateral-deficit | group_key: modules/cdp/cdp_erc20.vy | _push | sender-fee-collateral-deficit
code_smells: `_push` does not measure the collateral balance that the token deducts from the contract.
unverified: A supported collateral token must charge the sender an additional fee on outbound transfers.
description: A sender-fee token can reduce the contract balance by more than the recorded collateral payout.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: `_buy_surplus` computes `bought` from the current oracle price without a caller-supplied minimum.
unverified: Confirm whether transaction ordering around a supported oracle update permits another party to extract a material loss from a buyer.
description: A buyer can receive fewer stablecoins than expected when the oracle price changes before execution.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The below-110% branch requires `max_repay >= repay` and removes all shares, while the other branch permits a partial repayment.
unverified: Confirm that a reachable position requires more stablecoin than any available liquidator can supply and that this delay causes material loss.
description: A liquidator with only part of the required stablecoin cannot reduce an underwater position.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock
code_smells: `_withdraw` checks `_collat_ratio`, which reads the oracle whenever the borrower has debt.
unverified: Confirm a supported oracle outage and its duration for positions that retain excess collateral.
description: An oracle outage blocks a borrower with debt from withdrawing excess collateral.
