[Feynman: modules/cdp/cdp.vy] The module changes positions and stablecoin balances; its wrappers must send the collateral it calculates.

[Feynman: modules/cdp/cdp_erc20.vy] The wrapper takes collateral from the caller and sends collateral after the CDP changes its records; token behavior determines the actual balance change.

[Feynman: modules/cdp/cdp_native.vy] The wrapper receives native coin and sends it after the CDP changes its records; the receiver can execute code during the send.

[Feynman: modules/tokens/erc20.vy] The token tracks balances and allowances; its host must bind the module to the intended CDP state.

[Feynman: src/ministable.vy] The host binds and exports the token and native CDP modules; module exports determine which functions callers can reach.

[Socratic: modules/cdp/cdp_erc20.vy::_push — why?] What ensures that a successful transfer reduces the contract balance by exactly `amount`?

[Inversion: deposit] A caller can request zero, use a fee-charging token, or trigger a token callback before the deposit is credited.

[Inversion: _liquidate] A caller can choose a small `max_repay`, target a position below its debt value, or use a token that changes its outgoing transfer amount.

[Inversion: transferFrom] A caller can use zero allowance, maximum allowance, or transfer tokens during a collateral callback.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
code_smells: The module measures incoming collateral, but `_push` accepts a successful transfer without measuring the contract balance change.
unverified: Whether an accepted collateral token charges an additional fee to the sender, and whether deployed instances use that token.
description: A sender-paid token fee may reduce collateral held for other users when a caller receives collateral.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The low-collateral branch requires `max_repay >= repay` and burns the full `repay` from one caller.
unverified: Whether available liquidity or transaction routes prevent liquidators from assembling the required stablecoin balance.
description: A liquidator may fail to close a position when no caller can supply its full required repayment.
