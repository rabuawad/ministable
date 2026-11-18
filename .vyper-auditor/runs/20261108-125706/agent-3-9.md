[Feynman: cdp.vy] The module records collateral and debt, reads prices, and calculates payments; its first boundary assumption is that the oracle reports a usable price.

[Feynman: cdp_erc20.vy] The module receives and sends collateral tokens; its first boundary assumption is that a token transfer changes balances by the requested amount.

[Feynman: cdp_native.vy] The module receives and sends native coin; its first boundary assumption is that the receiver accepts a value call.

[Feynman: erc20.vy] The module records stablecoin balances and approvals; its first boundary assumption is that the imported signature recovery code rejects invalid signatures.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the accounting deduct the requested amount when the token can debit more or credit less?

[Inversion: _push] An attacker selects a sender-fee token, withdraws the full credited amount, and leaves another depositor with a shortfall.

[Inversion: redeem] A redeemer sets `min_paid`, a receiver-fee token credits less than `paid`, and the transfer still returns true.

[Inversion: _price] An attacker waits for a market move, an oracle answer at its floor, or a feed outage before calling a price-dependent function.

[Inversion: _liquidate] A caller supplies insufficient repayment, a token rejects a zero transfer, or a collateral token pauses transfers.

[Inversion: _accrue] A caller invokes `mint(0)` repeatedly, chooses update times, and changes the frequency of index updates.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow  
path: depositor → withdraw → accounting deducts the requested amount → token debits a larger amount → other depositors lose collateral  
boundary: `COLLATERAL.transfer(to, amount)`  
assumption: The token debits exactly `amount` from the contract.  
actual: A sender-fee token can debit more than `amount` and still return true.  
proof: Two users each deposit 100 tokens, so the contract holds 200 and records 200; a 10% sender fee makes one user's withdrawal of 100 debit 110, leaving 90 tokens against the other user's 100-token claim.  
description: A depositor can withdraw collateral with a sender fee and consume another depositor's collateral.  
fix: The module should reject an outgoing transfer when the contract balance decreases by more than the amount deducted from accounting.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage  
path: redeemer → redeem → `_redeem` checks gross `paid` → `_push` transfers collateral → redeemer receives less than `min_paid`  
boundary: `COLLATERAL.transfer(to, amount)`  
assumption: The receiver obtains the gross amount passed to the token.  
actual: A receiver-fee token can credit less than the gross amount and return true.  
proof: If `_redeem` calculates `paid = 100` and `min_paid = 100`, the check passes; a 10% receiver fee credits the redeemer only 90.  
description: A redeemer can receive less collateral than `min_paid` when the token charges a receiver fee.  
fix: The module should check the receiver's actual balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation  
code_smells: The underwater branch requires `max_repay >= repay` and clears the entire position in one call.  
unverified: The available liquidator balances and financing for a materially large underwater position need verification.  
description: A large underwater position can remain open when no liquidator can supply the full repayment.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert  
code_smells: The module calls `_push(msg.sender, seized)` when `seized` is zero.  
unverified: The selected collateral token must reject zero transfers, and a reachable position must produce a zero seizure.  
description: A collateral token can block a liquidation when it rejects a zero transfer.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: token-pause-blocks-liquidation | group_key: modules/cdp/cdp_erc20.vy | liquidate | token-pause-blocks-liquidation  
code_smells: The module requires the collateral token transfer to succeed before liquidation completes.  
unverified: The selected collateral token must support a pause or restriction that blocks transfers from the contract.  
description: A collateral token pause can block liquidators and leave undercollateralized debt open.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: redemption-oracle-lag-extraction | group_key: modules/cdp/cdp.vy | _redeem | redemption-oracle-lag-extraction  
code_smells: The module calculates collateral payments from the last accepted oracle answer and a capped redemption fee.  
unverified: A supported feed must report a price above the executable market price by more than the applicable fee and transaction costs.  
description: A redeemer can take excess borrower collateral when the oracle price exceeds the market price by more than the fee.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: zero-fee-oracle-swap | group_key: modules/cdp/cdp.vy | _buy_surplus | zero-fee-oracle-swap  
code_smells: The module values incoming collateral with the last accepted oracle answer and applies `SWAP_FEE`.  
unverified: A supported feed must overvalue collateral by more than `SWAP_FEE` and transaction costs.  
description: A buyer can receive excess surplus tokens when the oracle price exceeds the market price by more than the fee.

LEAD | contract: modules/cdp/cdp.vy | function: _cover_bad_debt | bug_class: zero-fee-oracle-swap | group_key: modules/cdp/cdp.vy | _cover_bad_debt | zero-fee-oracle-swap  
code_smells: The module values reserve collateral with the last accepted oracle answer and applies `SWAP_FEE`.  
unverified: A supported feed must undervalue collateral by more than `SWAP_FEE` and transaction costs while reserve and bad debt exist.  
description: A caller can receive excess reserve collateral when the oracle price falls below the market price by more than the fee.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: chainlink-min-answer-clamp | group_key: modules/cdp/cdp.vy | _price | chainlink-min-answer-clamp  
code_smells: The oracle check accepts every positive answer that meets the configured age limit.  
unverified: The selected aggregator must enforce a minimum answer above a reachable market price.  
description: An oracle floor can let borrowers mint against collateral at a price above its market value.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: immutable-oracle-no-fallback | group_key: modules/cdp/cdp.vy | _price | immutable-oracle-no-fallback  
code_smells: The module stores one immutable oracle and has no replacement or fallback path.  
unverified: The selected oracle must stop returning acceptable answers without recovery.  
description: An oracle outage can block price-dependent withdrawals, redemptions, and liquidations.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: caller-driven-compounding | group_key: modules/cdp/cdp.vy | _accrue | caller-driven-compounding  
code_smells: The module updates `rate_index` from its prior value, and any caller can invoke `mint(0)` to trigger an update.  
unverified: The deployment's fee, chain costs, and feasible call frequency must show a material excess charge.  
description: A caller can increase borrower interest by increasing the frequency of accrual updates.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path  
code_smells: The borrower supplies an exact `amount`, while `_accrue` updates debt before `_repay` checks that amount.  
unverified: A borrower must lack a practical way to predict the execution timestamp or submit a repayment through a helper.  
description: A borrower can retain debt or receive a revert when interest changes after the borrower obtains a repayment quote.
