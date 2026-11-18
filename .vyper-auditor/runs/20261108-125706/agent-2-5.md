[Feynman: modules/cdp/cdp.vy] The module records collateral, debt, surplus, and reserves; its accounting assumes each collateral payout removes exactly the recorded amount.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens; its accounting assumes the token’s reported transfer result describes the balance change.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin; its accounting assumes each successful native payout matches the recorded amount.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances, supply, allowances, and signatures; its accounting assumes its imported signature and domain modules enforce their stated rules.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the module measure the balance change on receipt but trust the requested amount on payout?

[Inversion: _push] A caller withdraws with a sender-fee token; a redeemer sets `min_paid` with a recipient-fee token; a liquidator receives a zero payout from a token that rejects zero transfers.

[Inversion: _liquidate] A caller offers less than the required full repayment; a position has debt greater than collateral value; a caller chooses a repayment that rounds seized collateral to zero.

[Inversion: _accrue] A caller invokes `mint(0)` each block; another caller waits for a long interval; a borrower repays after the debt quote changes.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: borrower → withdraw → accounting decreases by the requested amount → sender-fee token deducts more → other users have less collateral available
invariant: The token balance must cover the sum of recorded collateral and reserve.
violation_path: Two users each deposit 100 tokens → one user withdraws 100 tokens → the token deducts 101 tokens from the contract.
proof: Before withdrawal, the token balance and recorded collateral are both 200 tokens. `cdp._withdraw` reduces recorded collateral by 100, but `_push` only asserts `COLLATERAL.transfer(to, amount, default_return_value=True)`. With a 1% sender fee, the token balance becomes 99 while the other user retains a 100-token claim.
description: A borrower can withdraw with a sender-fee token and consume collateral that belongs to other users.
fix: The module should verify that each payout reduces its token balance by exactly the accounted amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: redeemer → redeem → `min_paid` checks the gross payout → recipient-fee token reduces the actual payout
invariant: A successful redemption must deliver at least `min_paid` collateral to the redeemer.
violation_path: A redeemer sets `min_paid` to 100 tokens → `_redeem` computes 100 tokens → the token charges a 1% recipient fee.
proof: `_redeem` asserts `paid >= min_paid` before `_push(msg.sender, paid)`. For `paid = min_paid = 100` and a 1% recipient fee, the call succeeds while the redeemer receives 99 tokens.
description: A recipient-fee token lets a redemption succeed when the redeemer receives less collateral than `min_paid`.
fix: The module should check the redeemer’s actual balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The branch below 110% collateralization requires one caller to repay the whole calculated amount.
unverified: Whether available liquidity and transaction limits prevent liquidators from funding a material position.
description: A large position can remain open when no liquidator can fund its required repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The partial liquidation branch floors `repay * LIQUIDATION_PENALTY // p` to collateral base units.
unverified: Whether a supported collateral price and position size make the zero payout materially affect liquidation incentives.
description: A liquidator can receive zero collateral for a repayment when the collateral unit is too coarse.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The module calls `_push` even when `_liquidate` returns zero collateral.
unverified: Whether a supported collateral token rejects zero transfers and a material position reaches a zero payout.
description: A collateral token that rejects zero transfers can block a liquidation with a zero payout.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: caller-driven-compounding | group_key: modules/cdp/cdp.vy | _accrue | caller-driven-compounding
code_smells: The module updates `rate_index` on each accrual, and `mint(0)` can trigger the update.
unverified: Whether the difference between feasible call frequencies causes material borrower loss under the deployed fee and chain conditions.
description: A caller can increase borrower debt by choosing more frequent interest updates.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The module accrues interest before it checks the caller’s fixed repayment amount.
unverified: Whether borrowers can reliably predict the execution timestamp or otherwise obtain enough stablecoin to close the remaining debt.
description: A borrower can retain debt after an interest update changes the quoted full repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _withdraw | bug_class: oracle-dependent-withdraw-lock | group_key: modules/cdp/cdp.vy | _withdraw | oracle-dependent-withdraw-lock
code_smells: The module checks the collateral ratio after withdrawal, and that check reads the oracle when debt remains.
unverified: The deployed oracle’s outage duration and whether affected borrowers can obtain enough stablecoin to repay their full debt.
description: An oracle outage can block a borrower from withdrawing excess collateral while debt remains.
