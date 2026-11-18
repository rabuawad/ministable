[Feynman: cdp._liquidate] The function removes debt and assigns collateral to a liquidator; its result depends on the wrapper sending the assigned collateral.

[Feynman: cdp_erc20._push] The function sends collateral tokens after the accounting changes; it assumes the token deducts exactly the requested amount.

[Feynman: cdp_erc20.redeem] The function burns a redeemer’s mUSD and sends collateral; it assumes the token recipient receives the amount checked against `min_paid`.

[Feynman: cdp._buy_surplus] The function exchanges collateral for protocol-held mUSD; it assumes the buyer accepts the output at execution time.

[Inversion: cdp_erc20._push] A caller can withdraw their deposit, liquidate another position, or redeem another position when the token charges a sender fee.

[Inversion: cdp_erc20.redeem] A caller can set `min_paid`, use a token that charges the recipient a fee, or submit the transaction before the token changes its fee.

[Inversion: cdp._liquidate] A caller can choose a small `max_repay`, target a position below 110%, or wait until the collateral price falls further.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the accounting assume that the contract loses only `amount` when the token determines the actual balance decrease?

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
seam: economics×asymmetry
actor: A depositor, liquidator, redeemer, or bad-debt cover caller.
root_cause: `_push` does not check the contract’s actual collateral balance decrease after the token transfer.
path: Caller → `withdraw`, `liquidate`, `redeem`, or `cover_bad_debt` → accounting deducts `amount` → token deducts `amount` plus a sender fee → remaining collateral no longer covers other users’ claims.
proof: If the contract holds 1,100 tokens against 1,100 recorded tokens and a withdrawal deducts 100 from the caller’s claim, a 1% sender fee removes 101 tokens; the contract holds 999 against 1,000 recorded tokens. The same `_push` serves each payout route.
description: A caller can trigger sender fees that consume collateral assigned to other users.
fix: Reject an outgoing transfer unless the contract balance decreases by exactly `amount`.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
seam: economics×asymmetry
actor: A redeemer who uses collateral that charges a recipient transfer fee.
root_cause: `redeem` checks `min_paid` against the amount debited from the position instead of the amount received by the redeemer.
path: Redeemer → `redeem(user, amount, min_paid)` → `_redeem` checks the nominal payout → `_push` transfers tokens with a recipient fee → redeemer receives less than `min_paid`.
proof: If `_redeem` calculates `paid = 100` and `min_paid = 100`, the check passes; a 2% recipient fee makes the redeemer receive 98 while the borrower’s collateral decreases by 100.
description: A redeemer receives fewer collateral tokens than `min_paid` when the token charges a recipient fee.
fix: Check the redeemer’s actual balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
seam: access×economics
code_smells: The function requires one caller to provide the full `repay` when collateral value is below 110% of debt.
unverified: Whether available mUSD liquidity and transaction financing can cover a large position before its collateral value falls further.
description: A large borrower can retain an unhealthy position when no liquidator can fund the required repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
seam: economics×asymmetry
code_smells: The buyer supplies collateral, but the function accepts no minimum mUSD output.
unverified: Whether a buyer submits a transaction across an oracle update that reduces the output below their acceptable amount.
description: A buyer can receive fewer mUSD than expected when the oracle price changes before execution.
