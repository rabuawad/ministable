[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, and reserves; its first external assumption is that the oracle price represents the collateral’s current value.

[Feynman: modules/cdp/cdp_erc20.vy] The wrapper receives and sends collateral tokens; its first external assumption is that a successful transfer removes and delivers the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The wrapper receives and sends native coin; its first language-specific assumption is that its protected entry points share the expected lock with exported module functions.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances and permits; its first external assumption is that signature recovery returns the intended signer.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the wrapper measure the incoming balance change but not the outgoing balance change?

[Inversion: redeem] An attacker can choose the target position, choose an amount near `min_paid`, or wait for a collateral token fee to change.

[Inversion: liquidate] A caller can supply a small `max_repay`, target a position below 100% collateralization, or use a collateral token that rejects zero transfers.

[Inversion: buy_surplus] A buyer can submit before an oracle update, pay with a fee-charging token, or encounter a smaller surplus after another transaction.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
seam: execution×periphery
path: collateral holder → withdraw → accounting removes the requested amount → token removes an additional sender fee → other collateral claims exceed the token balance
trace: `withdraw` → `cdp._withdraw` → `_push` → collateral token `transfer` → remaining claims exceed the contract balance.
violated_principle: The contract must retain the collateral it records for other users.
root_cause: `_push` accepts a successful transfer without checking how much collateral leaves the contract.
proof: If Alice and Bob each hold 100 credited tokens, the contract holds 200; Alice withdraws 100 with a 1% sender fee, leaving 99 tokens against Bob’s 100-token claim.
description: A withdrawing user can consume other users’ collateral when the token charges an extra sender fee.
fix: The wrapper should reject a transfer when its balance decreases by more than the amount debited from accounting.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
seam: three-way
path: redeemer → redeem → gross output passes `min_paid` → collateral token deducts a recipient fee → redeemer receives less than the minimum
trace: `redeem` → `cdp._redeem` checks `paid >= min_paid` → `_push` calls the collateral token → the recipient receives less than `paid`.
violated_principle: A successful redemption must deliver at least `min_paid` collateral to the redeemer.
root_cause: The wrapper checks the gross transfer amount before it observes the recipient’s net collateral receipt.
proof: With `paid = min_paid = 100` and a 1% recipient fee, the check passes, the debt and stablecoin are reduced, and the redeemer receives 99 tokens.
description: A redeemer receives less than `min_paid` when the collateral token deducts a recipient fee.
fix: The wrapper should check the recipient’s balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The branch below 110% collateralization requires `max_repay >= repay` and clears all debt shares in one call.
unverified: The available liquidator balances, flash liquidity, and resulting delay for a material position require verification.
description: A large position can require more stablecoin than an available liquidator holds.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: The purchase uses the oracle price at execution and accepts no minimum stablecoin output.
unverified: The magnitude and timing of price changes during submitted purchases require verification.
description: A buyer can receive fewer stablecoins than expected after the oracle price changes.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The wrapper always calls `_push`, even when `cdp._liquidate` returns zero collateral.
unverified: A supported deployed collateral token must reject zero transfers, and a material liquidation must reach a zero payout.
description: A collateral token that rejects zero transfers can block a liquidation with a zero payout.
