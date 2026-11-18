[Feynman: cdp.vy] The module records collateral and debt, charges interest, and calculates collateral payments; its price reads assume the oracle reports a usable market price.

[Feynman: cdp_erc20.vy] The module receives and sends collateral tokens; its balance accounting assumes an outgoing transfer removes exactly the requested amount.

[Feynman: cdp_native.vy] The module receives and sends native coin; its payment paths assume the receiver accepts the call.

[Feynman: erc20.vy] The module records stablecoin balances, allowances, and permits; its signature path assumes the imported recovery and domain modules enforce their stated rules.

[Socratic: cdp_erc20.vy:_push — why?] Why does the module measure incoming collateral but trust the requested amount for outgoing collateral?

[Inversion: _push] A caller withdraws through a sender-fee token; a redeemer receives through a recipient-fee token; a token pauses before liquidation.

[Inversion: _liquidate] A caller selects a position with coarse collateral; a borrower opens a small position; a large position has less collateral value than debt.

[Inversion: _price] An oracle reports its minimum answer; a feed stops updating; a price changes before a pending purchase executes.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow  
path: borrower → withdraw → `_push` transfers collateral and charges an extra sender fee → other borrowers lose collateral backing  
proof: Alice and Bob each deposit 100 tokens. A token charges the sender 10% extra on transfers. Alice withdraws 100; accounting removes 100 from Alice, but `_push` removes 110 from the contract. Bob retains a claim for 100 while the contract holds 90. The same `_push` serves `liquidate`, `redeem`, and `cover_bad_debt`.  
description: A borrower can withdraw collateral through a sender-fee token and consume collateral that belongs to other borrowers.  
fix: The module should reject transfers that decrease its balance by more than the accounted amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage  
path: redeemer → `redeem` → `_redeem` checks nominal payout → `_push` transfers through a recipient-fee token → redeemer receives less than `min_paid`  
proof: `_redeem` checks `paid >= min_paid` before `_push`. With `paid = min_paid = 100` tokens and a 10% recipient fee, the call succeeds while the redeemer receives 90 tokens and burns the full stablecoin amount.  
description: A redeemer can receive less collateral than `min_paid` when the collateral token charges a recipient fee.  
fix: The module should check the recipient’s actual balance increase against `min_paid`.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation  
code_smells: The underwater branch requires `max_repay >= repay` and clears all debt shares in one call.  
unverified: The available stablecoin liquidity and transaction financing for a position large enough to delay liquidation.  
description: A large underwater position can require more stablecoin than any liquidator can obtain for one transaction.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize  
code_smells: The partial branch computes `seized = repay * LIQUIDATION_PENALTY // p` and permits a zero result.  
unverified: A supported collateral price and position size that make a zero payout economically significant.  
description: A liquidator can receive zero collateral when the collateral unit has a high value.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: zero-share-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | zero-share-liquidation  
code_smells: `_repay` removes `amount * PRECISION // rate_index` shares for a partial repayment.  
unverified: A reachable index and position size that make repeated zero-share repayments materially harmful.  
description: A liquidator can burn stablecoin without reducing debt shares when the repayment rounds down to zero shares.

LEAD | contract: modules/cdp/cdp.vy | function: mint | bug_class: no-minimum-debt | group_key: modules/cdp/cdp.vy | mint | no-minimum-debt  
code_smells: `mint` accepts a position with any positive debt amount and has no minimum debt.  
unverified: The collateral price, gas cost, and position count needed to create material unpaid debt.  
description: A borrower can open a position whose liquidation reward is less than the liquidator’s cost.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: chainlink-min-answer-clamp | group_key: modules/cdp/cdp.vy | _price | chainlink-min-answer-clamp  
code_smells: `_price` accepts every positive answer within `ORACLE_TIMEOUT`, including an aggregator floor.  
unverified: The selected feed’s bounds and whether its market price can fall below its reported floor.  
description: An oracle floor can let a borrower mint stablecoin against collateral worth less than the reported value.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: immutable-oracle-no-fallback | group_key: modules/cdp/cdp.vy | _price | immutable-oracle-no-fallback  
code_smells: `ORACLE` is immutable, and `_price` rejects an answer older than `ORACLE_TIMEOUT`.  
unverified: Whether the selected feed can stop permanently without a migration path for this deployment.  
description: A stopped oracle can block liquidation and other calls that require a collateral price.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock  
code_smells: `_withdraw` calls `_collat_ratio`, which reads the oracle when the borrower retains debt.  
unverified: The duration of a feed outage and the borrower’s access to enough stablecoin to repay all debt.  
description: An oracle outage can block a borrower from withdrawing surplus collateral while the position retains debt.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage  
code_smells: `_buy_surplus` calculates `bought` from the current oracle answer and accepts no minimum output.  
unverified: Whether a pending buyer can receive materially less stablecoin after an oracle update at execution.  
description: An oracle update can reduce the stablecoin a buyer receives for a pending surplus purchase.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: redemption-oracle-lag-extraction | group_key: modules/cdp/cdp.vy | _redeem | redemption-oracle-lag-extraction  
code_smells: `_redeem` accepts an oracle answer until `ORACLE_TIMEOUT` and charges a bounded fee.  
unverified: A supported feed’s update delay and a market move that exceeds the redemption fee.  
description: A redeemer can take excess borrower collateral when the market price rises beyond the oracle price and fee.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert  
code_smells: `liquidate` calls `_push` even when `seized` equals zero.  
unverified: A supported collateral token that rejects zero transfers and a reachable liquidation with zero seized collateral.  
description: A collateral token that rejects zero transfers can make a zero-payout liquidation revert.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: token-pause-blocks-liquidation | group_key: modules/cdp/cdp_erc20.vy | liquidate | token-pause-blocks-liquidation  
code_smells: `liquidate` requires the collateral token transfer to succeed after it calculates the repayment.  
unverified: Whether a selected collateral token can pause transfers and how long that pause can last.  
description: A token issuer can block liquidation while the collateral token rejects transfers.
