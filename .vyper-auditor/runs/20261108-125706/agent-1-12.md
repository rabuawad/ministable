[Feynman: modules/cdp/cdp.vy] The module tracks collateral and debt, then tells a wrapper how much collateral to send. The wrapper must deliver the amount that the module calculates.

[Feynman: modules/cdp/cdp_erc20.vy] The wrapper measures tokens received on deposits and sends tokens after the accounting changes. The unexplained assumption is that a transfer delivers its nominal amount.

[Feynman: modules/cdp/cdp_native.vy] The wrapper accepts native coin and sends the amounts calculated by the shared module. Its exported functions depend on the shared module’s state.

[Feynman: modules/tokens/erc20.vy] The module records stablecoin balances, allowances, supply, and signatures. Its host determines which functions are exported.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does a successful token transfer prove that the recipient received the amount checked by `min_paid`?

[Inversion: redeem] A caller sets `min_paid` to the calculated amount; a collateral token deducts a transfer fee; a healthy position supplies the collateral.

[Inversion: _push] A caller withdraws collateral; a token charges the sender an extra fee; other users retain claims against the same token balance.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
seam: three-way
path: redeemer → `redeem` → nominal `min_paid` check → collateral `transfer` deducts a fee → redeemer receives less than `min_paid`
trace: `cdp._redeem` checks nominal `paid` → `_push` calls `COLLATERAL.transfer` → the token deducts its fee → `redeem` returns nominal `paid`
violated_principle: `redeem` promises to revert when the collateral paid is less than `min_paid`, and the wrapper states that it supports fee-on-transfer collateral.
proof: With 6-decimal collateral at $1, a healthy position has 200 tokens of collateral and 100 mUSD of debt. A 50 mUSD redemption has a 1% redemption fee and calculates `paid = 49.5` tokens. The caller sets `min_paid = 49.5`; the check passes. If the token deducts a 1% fee from the transfer, the caller receives 49.005 tokens, while `redeem` returns 49.5.
description: The wrapper accepts a fee on transfer, so a redeemer receives less collateral than `min_paid` permits.
fix: The wrapper should check the recipient’s balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
code_smells: The wrapper reduces a user’s collateral by `amount` and does not measure the contract’s token balance after `_push`.
unverified: Whether an intended collateral token charges an additional fee to the sender on outgoing transfers.
description: A sender-paid token fee can reduce the contract’s balance below the collateral that other users own.
