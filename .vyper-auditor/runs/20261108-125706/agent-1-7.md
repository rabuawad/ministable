[Feynman: modules/cdp/cdp.vy] The module records collateral, debt, interest, liquidations, and redemptions; its accounting assumes debt shares and token supply remain aligned.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens; it assumes a successful token transfer delivers the stated amount.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin; it assumes callers can receive the requested payment.

[Feynman: modules/tokens/erc20.vy] The module records stablecoin balances and allowances; its permit path assumes the signature recovery module validates signatures correctly.

[Socratic: modules/cdp/cdp.vy:_buy_surplus — why?] What protects a buyer when the oracle price changes before the purchase executes?

[Inversion: _buy_surplus] A caller submits a fixed collateral payment; an oracle update lowers the price; another buyer consumes the available surplus first.

[Inversion: _push] A token charges the receiver a fee; a token charges the sender an extra fee; a token rejects a zero transfer.

[Inversion: burn] A borrower reads their debt; time advances before execution; interest increases the debt above the submitted amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: buy_surplus | bug_class: missing-minimum-purchase-output | group_key: modules/cdp/cdp_erc20.vy | buy_surplus | missing-minimum-purchase-output
path: buyer → buy_surplus → _pull → cdp._buy_surplus → purchase executes at a lower oracle price without a minimum output
assumption: The buyer accepts the oracle price at execution.
violation: The oracle price falls after the buyer submits the transaction.
proof: With 18-decimal collateral and a price of $2,000, a payment of 1 token quotes 1,990 mUSD after the 0.5% fee. If the oracle updates to $1,600 before execution, the same payment returns 1,592 mUSD. The function accepts no minimum output, so the buyer receives 398 mUSD less than the earlier quote.
description: A buyer receives fewer stablecoins than expected when the oracle price falls before the purchase executes.
fix: Add a minimum output argument and revert when the purchase returns less than that amount.

FINDING | contract: modules/cdp/cdp_native.vy | function: buy_surplus | bug_class: missing-minimum-purchase-output | group_key: modules/cdp/cdp_native.vy | buy_surplus | missing-minimum-purchase-output
path: buyer → buy_surplus → cdp._buy_surplus → purchase executes at a lower oracle price without a minimum output
assumption: The buyer accepts the oracle price at execution.
violation: The oracle price falls after the buyer submits the transaction.
proof: A payment of 1 native coin returns 1,990 mUSD at $2,000 and 1,592 mUSD at $1,600, after the 0.5% fee. The payable entry point accepts no minimum output.
description: A buyer receives fewer stablecoins than expected when the oracle price falls before the purchase executes.
fix: Add a minimum output argument and revert when the purchase returns less than that amount.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
code_smells: The module checks the token return value but does not measure the recipient’s balance increase or the contract’s balance decrease.
unverified: The deployed collateral token and its outbound fee rules are unknown.
description: A collateral token can charge an outbound fee, so a recipient gets less collateral than the module records.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The function requires an exact amount and accrues interest before it repays debt.
unverified: The stability fee and transaction timing must produce an increase between the borrower’s debt quote and execution.
description: A borrower can retain debt after a repayment when interest increases before the transaction executes.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The branch below 110% collateral requires `max_repay >= repay` and clears all debt shares in one call.
unverified: Available liquidator balances and financing determine whether a large position remains open.
description: A liquidator must provide the full repayment to close a position below 110% collateral.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: caller-driven-compounding | group_key: modules/cdp/cdp.vy | _accrue | caller-driven-compounding
code_smells: The function updates `rate_index`, and subsequent accruals calculate interest from the updated index.
unverified: The intended interest convention and the material effect at the deployed fee and call frequency are unknown.
description: A caller can increase the frequency of interest accrual and increase the debt that borrowers owe.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock
code_smells: The function calls `_collat_ratio`, which reads the oracle whenever the borrower has debt.
unverified: The duration and recovery path of a deployed oracle outage are unknown.
description: An oracle outage can prevent a borrower with debt from withdrawing collateral.

LEAD | contract: modules/cdp/cdp.vy | function: mint | bug_class: no-minimum-debt | group_key: modules/cdp/cdp.vy | mint | no-minimum-debt
code_smells: The function accepts debt amounts without a minimum position size.
unverified: Collateral value, gas costs, and liquidator incentives determine whether small positions remain open.
description: A borrower can create a position whose liquidation reward is smaller than the liquidator’s costs.
