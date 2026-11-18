[Feynman: modules/cdp/cdp.vy] The module records collateral, debt shares, interest, liquidation, and redemption. The accounting assumes that token supply and debt remain compatible after each rounded update.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives collateral tokens and sends them after the CDP module changes its records. The accounting assumes that a transfer removes the recorded amount from the contract.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin around the shared CDP accounting. Its calls use the shared module’s protected entry points.

[Feynman: modules/tokens/erc20.vy] The module records stablecoin balances, allowances, supply, and permits. Its exported functions retain the module’s own nonreentrancy setting.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the module measure collateral received but not collateral removed or received on an outgoing transfer?

[Inversion: _push] An attacker can choose a sender-fee token at deployment, withdraw after another user deposits, or trigger an outgoing liquidation transfer.

[Inversion: _liquidate] A liquidator can choose a partial repayment, encounter collateral worth less than 110% of debt, or call when the collateral payout rounds to zero.

[Inversion: _buy_surplus] A buyer can submit before an oracle update, pay a fee-charging token, or receive a lower output after an oracle update.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow  
pair_or_branch: `_pull` / `_push`  
asymmetry: `_pull` credits the actual balance increase, while `_push` does not check the contract’s balance decrease.  
path: borrower → `withdraw` → `_push` → sender fee consumes collateral recorded for another borrower  
proof: Assume a supported token charges the sender 10% on transfers and charges no fee to the recipient. Alice and Bob each deposit 100 tokens, so the contract holds 200 and records 100 for each. Alice withdraws 100; `cdp._withdraw` removes 100 from Alice’s record, while `_push` transfers 100 and the token removes 110. The contract holds 90 against Bob’s recorded 100, so Bob’s full withdrawal fails.  
description: A borrower can make a sender-fee token consume another borrower’s collateral.  
fix: The module must reject an outgoing transfer when the contract balance decreases by more than the recorded amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage  
pair_or_branch: `_pull` / redemption payout  
asymmetry: `_pull` measures the actual received amount, while `redeem` checks `min_paid` before the recipient receives tokens.  
path: redeemer → `redeem` → gross payout passes `min_paid` → transfer fee reduces the received collateral  
proof: If `cdp._redeem` calculates `paid = 100` and the caller sets `min_paid = 100`, its check passes. With a 10% recipient transfer fee, `_push` sends 100 but the caller receives 90, and `redeem` returns 100.  
description: A transfer-fee token gives a redeemer less collateral than the minimum they specify.  
fix: The module must check the recipient’s balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation  
code_smells: The low-collateral branch requires one caller to supply the full `repay`, while the other branch accepts `max_repay`.  
unverified: The available liquidator capital and market liquidity must be checked for a position large enough to prevent liquidation.  
description: A large position can remain open when no liquidator holds enough stablecoin for its required repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: zero-share-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | zero-share-liquidation  
code_smells: A partial liquidation burns `repay` even when `_repay` removes zero shares.  
unverified: A material loss requires a reachable index, collateral price, and repayment size that make the repeated loss exceed rounding dust.  
description: A liquidator can burn stablecoin without reducing the borrower’s debt shares.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage  
code_smells: The surplus purchase accepts collateral without a minimum stablecoin output.  
unverified: The execution path must demonstrate a material oracle change between the buyer’s quote and transaction.  
description: A buyer can receive fewer stablecoins than expected after an oracle update.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path  
code_smells: `burn` accepts an exact amount, while `_accrue` can increase the debt before `_repay` checks it.  
unverified: The effect on a borrower’s ability to close a position requires a concrete transaction timing and available stablecoin trace.  
description: A borrower can retain debt when interest increases after the borrower obtains a repayment quote.
