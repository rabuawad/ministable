[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, liquidations, and redemptions; its price calculations assume the oracle reports the intended collateral value.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives collateral tokens and sends them to callers; its transfer calls assume the token’s balance changes match its return value.

[Feynman: modules/cdp/cdp_native.vy] The module receives native coin and sends it to callers after the accounting update; its payout path assumes the recipient accepts the call.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances, allowances, and permits; its signature path assumes the imported recovery and domain modules enforce their stated rules.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does a successful token transfer prove that the contract lost exactly `amount`?

[Inversion: _push] An attacker withdraws with a sender-fee token; a redeemer uses a recipient-fee token; a token rejects a zero transfer.

[Inversion: _price] An attacker trades before an oracle update; a feed reports its minimum answer; a feed stops reporting.

[Inversion: _liquidate] A caller supplies a small `max_repay`; a position has less collateral value than debt; a token rejects the resulting zero payout.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow  
path: borrower → `withdraw` → `_withdraw` debits the requested amount → `_push` transfers collateral and consumes another borrower’s collateral  
boundary: `COLLATERAL.transfer(to, amount)`  
assumption: A successful transfer reduces the contract’s token balance by exactly `amount`.  
actual: A token with a sender fee reduces the balance by more than `amount`.  
proof: Two borrowers each deposit 100 tokens, so the contract holds 200 and owes 200. A token with a 10% sender fee makes `withdraw(100)` reduce the contract balance by 110, while `_withdraw` reduces the first borrower’s accounting by 100. The contract then holds 90 and owes the second borrower 100. The same `_push` serves liquidation, redemption, and bad-debt coverage.  
description: A borrower can withdraw with a sender-fee token and consume collateral that belongs to other borrowers.  
fix: The contract should reject any outgoing transfer that reduces its token balance by more than the accounted amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage  
path: redeemer → `redeem` → `_redeem` checks nominal `paid` against `min_paid` → `_push` transfers less to the redeemer  
boundary: `COLLATERAL.transfer(msg.sender, paid)`  
assumption: The redeemer receives the nominal `paid` amount.  
actual: A recipient-fee token credits the redeemer with less than `paid`.  
proof: If `_redeem` calculates `paid = 100` and the caller sets `min_paid = 100`, the check passes. A token that deducts a 10% recipient fee credits 90, while `redeem` returns 100 and the caller’s mUSD is burned.  
description: A recipient-fee token gives a redeemer less collateral than the minimum they set.  
fix: The contract should check the redeemer’s actual balance increase against `min_paid`.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert  
code_smells: The function calls `_push` even when `_liquidate` returns zero collateral.  
unverified: The deployed collateral token must reject zero transfers, and a reachable position must produce zero `seized`.  
description: A token that rejects zero transfers can make a liquidator’s call revert.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation  
code_smells: The function requires `max_repay >= repay` for the branch below 110% collateralization.  
unverified: The available liquidators may lack sufficient mUSD in one balance when a large position enters this branch.  
description: A large position can require more mUSD than one liquidator holds.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage  
code_smells: The function calculates `bought` from the current oracle price without a caller-supplied minimum.  
unverified: A price update must reduce `bought` between the buyer’s transaction submission and execution.  
description: An oracle update can give a surplus buyer fewer mUSD than the buyer expects.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: redemption-oracle-lag-extraction | group_key: modules/cdp/cdp.vy | _redeem | redemption-oracle-lag-extraction  
code_smells: The function pays collateral at the latest accepted oracle price with a fee of at most 5%.  
unverified: The market price must fall below the accepted oracle price by more than the applicable redemption fee.  
description: A redeemer can receive excess borrower collateral when the accepted oracle price exceeds the market price enough.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: chainlink-min-answer-clamp | group_key: modules/cdp/cdp.vy | _price | chainlink-min-answer-clamp  
code_smells: The function accepts every positive, recent oracle answer without a feed-specific lower bound.  
unverified: The selected feed must impose a minimum answer above the collateral’s market price.  
description: An oracle floor can let borrowers receive excess mUSD against collateral.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: immutable-oracle-no-fallback | group_key: modules/cdp/cdp.vy | _price | immutable-oracle-no-fallback  
code_smells: The function reads an immutable oracle and has no replacement or fallback path.  
unverified: The configured oracle must stop returning acceptable answers permanently.  
description: A retired oracle can block price-dependent actions for borrowers and liquidators.
