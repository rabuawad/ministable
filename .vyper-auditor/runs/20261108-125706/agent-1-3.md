[Feynman: modules/cdp/cdp.vy] The module records collateral, debt, interest, liquidations, and redemptions; it assumes the collateral transfer matches its accounting.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens; it assumes an outgoing transfer removes exactly the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin; it assumes the caller can receive each payment.

[Feynman: modules/tokens/erc20.vy] The module records stablecoin balances and approvals; it assumes the host binds the intended token state.

[Socratic: modules/cdp/cdp_erc20.vy._push — why?] Why does the module measure incoming collateral but assume the token debits exactly the requested outgoing amount?

[Inversion: _push] A token can charge the sender an extra fee, charge the recipient a fee, or reject a zero transfer.

[Inversion: _liquidate] A caller can select a small `max_repay`, target a deeply underwater position, or act when collateral units have a high value.

[Inversion: _buy_surplus] A buyer can act after the market price falls, pay one collateral unit, or wait for a small surplus residue.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: borrower → `withdraw` → `_withdraw` debits the requested collateral → `_push` sends collateral and the token charges an extra sender fee → other deposits lose backing
proof: The module accepts fee-on-transfer collateral and credits measured inflows. With a token that charges the sender 10% extra, two users each deposit 100 tokens and receive 100 credits. The first user withdraws 100; `_push` debits 110 from the contract while accounting removes only 100. The contract holds 90 tokens against the second user’s 100-token claim. The same `_push` path serves `liquidate`, `redeem`, and `cover_bad_debt`.
description: A sender-side transfer fee removes other users’ collateral because the module debits only the requested amount.
fix: The module should reject any outgoing transfer that reduces its balance by more than the accounted amount.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | redeem | fee-on-transfer-outflow
code_smells: The function checks `min_paid` before `_push`, and `_push` does not measure the tokens that the recipient receives.
unverified: Confirm that a supported collateral token charges the recipient a transfer fee and that users rely on `min_paid` as a received-token minimum.
description: A recipient-side transfer fee can give a redeemer fewer tokens than `min_paid`.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The underwater branch requires `max_repay >= repay` and burns the full `repay` from one caller.
unverified: Confirm that available liquidators cannot obtain or combine enough mUSD to close a material underwater position.
description: A large underwater position can prevent liquidators with smaller balances from reducing its debt.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The partial branch calculates `seized = repay * LIQUIDATION_PENALTY // p`, which can equal zero for a positive repayment.
unverified: Confirm a supported collateral price and position size for which the zero payout prevents a material liquidation.
description: A liquidator can receive zero collateral for a positive repayment when collateral units have a high value.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: zero-fee-oracle-swap | group_key: modules/cdp/cdp.vy | _buy_surplus | zero-fee-oracle-swap
code_smells: The function prices collateral at the latest accepted oracle answer and applies a fixed 0.5% fee.
unverified: Confirm that a supported collateral market can move more than 0.5% before an accepted oracle answer updates.
description: A buyer can receive surplus mUSD at an outdated price when the market moves beyond the fee.

LEAD | contract: modules/cdp/cdp.vy | function: _cover_bad_debt | bug_class: zero-fee-oracle-swap | group_key: modules/cdp/cdp.vy | _cover_bad_debt | zero-fee-oracle-swap
code_smells: The function pays reserve collateral at the latest accepted oracle answer and applies a fixed 0.5% fee.
unverified: Confirm that a supported collateral market can move more than 0.5% before an accepted oracle answer updates.
description: A caller can receive excess reserve collateral when the market moves beyond the fee.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: redemption-oracle-lag-extraction | group_key: modules/cdp/cdp.vy | _redeem | redemption-oracle-lag-extraction
code_smells: The function prices a redemption at the latest accepted oracle answer and applies a fee that starts at 0.5%.
unverified: Confirm that a supported collateral market can rise beyond the applicable fee before the oracle answer updates.
description: A redeemer can receive excess borrower collateral when the market rises beyond the fee.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The function accepts an exact `amount`, while `_repay` rejects an amount above the debt and interest can increase the debt before execution.
unverified: Confirm that a borrower cannot reliably predict the execution timestamp or use another transaction path to clear all shares.
description: A borrower can fail to clear all debt when interest changes the debt before the transaction executes.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: token-pause-blocks-liquidation | group_key: modules/cdp/cdp_erc20.vy | liquidate | token-pause-blocks-liquidation
code_smells: The function requires `_push` to transfer collateral before the liquidation transaction can finish.
unverified: Confirm that a deployed collateral token can pause transfers for the contract and that a pause can outlast a material price move.
description: A collateral token pause can prevent liquidators from closing unhealthy positions.
