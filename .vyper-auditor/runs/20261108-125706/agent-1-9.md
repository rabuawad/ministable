[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens for positions; it assumes a successful token call has the expected balance effects.

[Feynman: modules/cdp/cdp_native.vy] The module receives native coin and sends collateral after the CDP module updates its accounts; it assumes the receiver accepts the call.

[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, liquidations, and redemptions; it assumes the oracle returns a usable price.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances and allowances; it assumes its signature dependency recovers the intended signer.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the module check the token’s return value but not the amount debited or received?

[Inversion: _push] A caller withdraws through a token that charges the recipient; a caller withdraws through a token that charges the sender; a caller receives zero tokens after a rounded transfer.

[Inversion: _price] A feed returns its minimum answer; a feed stops updating; a sequencer feed reports downtime.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow  
path: redeemer → redeem → _redeem checks nominal `paid` → _push transfers collateral → redeemer receives less than `min_paid`  
boundary: `COLLATERAL.transfer(to, amount, default_return_value=True)` with a recipient-fee token  
assumption: A successful transfer gives the recipient the nominal `amount`.  
actual: A token can return `True` while deducting a fee from the recipient’s amount.  
proof: For `paid = 100` token units and `min_paid = 100`, `_redeem` passes `assert paid >= min_paid`; a token with a 10% recipient fee credits only 90 units, while `redeem` returns 100. The module documentation explicitly supports tokens that charge a transfer fee.  
description: The module checks nominal collateral, so a redeemer can receive less than `min_paid`.  
fix: The module should measure the recipient’s balance increase and enforce `min_paid` against that increase.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow  
code_smells: The module debits the position by `amount` and does not measure the collateral balance after `transfer`.  
unverified: A deployed collateral token must charge the sender more than `amount`; then a withdrawal can consume collateral accounted to other users.  
description: A sender-fee token can reduce the collateral held for other users.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: token-pause-blocks-liquidation | group_key: modules/cdp/cdp_erc20.vy | liquidate | token-pause-blocks-liquidation  
code_smells: The module sends seized collateral in the same transaction as the debt update.  
unverified: The selected collateral token must permit its administrator to pause transfers or block the liquidator.  
description: A token administrator can block liquidations if the token rejects collateral transfers.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert  
code_smells: The module calls `_push` when `_liquidate` returns `seized = 0`.  
unverified: The selected collateral token must reject zero transfers, and a position must reach the zero-seizure branch.  
description: A token that rejects zero transfers can block a liquidation that seizes zero collateral.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: chainlink-min-answer-clamp | group_key: modules/cdp/cdp.vy | _price | chainlink-min-answer-clamp  
code_smells: The function accepts every positive answer within `ORACLE_TIMEOUT`.  
unverified: The selected feed must clamp its answer at a minimum above the collateral’s market price.  
description: A feed that clamps its answer can give callers a price above the collateral’s market price.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: immutable-oracle-no-fallback | group_key: modules/cdp/cdp.vy | _price | immutable-oracle-no-fallback  
code_smells: The function reads one immutable oracle and rejects answers older than `ORACLE_TIMEOUT`.  
unverified: The configured feed must stop providing current answers without an external recovery path.  
description: A retired feed can block price-dependent position operations.
