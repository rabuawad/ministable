[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, and liquidation; its accounting assumes token supply and debt use the same units.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral; its accounting assumes each outgoing transfer reduces its token balance by the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The module receives native coin and sends it after the shared accounting changes; the call must complete for those changes to persist.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances and supply; its metadata determines how users and integrations interpret those balances.

[Feynman: src/ministable.vy] The host binds the native CDP and stablecoin modules; its constructor assumes the supplied stablecoin decimals match the CDP’s units.

[Socratic: modules/cdp/cdp_erc20.vy:759 — why?] Why does `_push` accept a transfer without checking how much collateral leaves the contract?

[Inversion: _push] A caller withdraws through a sender-fee token; a redeemer uses a recipient-fee token; a liquidator receives less than the quoted seizure.

[Inversion: _liquidate] A caller supplies a small `max_repay`; a position has coarse collateral units; a position has collateral worth less than its debt.

[Inversion: __init__] A deployer supplies 6 decimals; a user mints against native collateral; an integration interprets the minted balance using the token metadata.

FINDING | contract: src/ministable.vy | function: __init__ | bug_class: unchecked-stablecoin-decimals | group_key: src/ministable.vy | __init__ | unchecked-stablecoin-decimals
path: deployer → `__init__` with `decimals_ = 6` → ERC-20 metadata reports 6 decimals while CDP accounting uses 18 → users and integrations value the supply incorrectly
invariant: One displayed stablecoin unit must equal the unit of debt and USD value used by the CDP.
violation_path: Deploy with `decimals_ = 6` → deposit $1.50 of collateral → mint `10**18` base units.
proof: `erc20.__init__` stores the supplied `decimals_`; `cdp.mint` and `_collat_ratio` use 18-decimal debt amounts. The position owes one 18-decimal accounting unit, while ERC-20 metadata identifies the minted balance as `10**12` tokens.
description: The deployer can set six decimals, so users and integrations see one dollar of debt as one trillion stablecoin units.
fix: Require `decimals_ == 18` in the constructor.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: caller → `withdraw` → `_push` → a sender-fee token deducts more than the accounting debit → other depositors lose collateral
invariant: The contract’s collateral balance must cover all recorded collateral and reserve balances.
violation_path: Two users each deposit 100 tokens → one user withdraws 100 → the token deducts 110 from the contract.
proof: `_pull` credits the actual balance increase, but `_push` only asserts the return value of `transfer(to, amount)`. With a 10-token sender fee, the contract holds 90 tokens after the withdrawal while the other user retains a claim for 100; that user’s full withdrawal fails.
description: A caller can withdraw through a sender-fee token and leave other users with claims that exceed the contract’s token balance.
fix: Reject outgoing transfers unless the contract’s token balance decreases by exactly `amount`.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: redeemer → `redeem` → `min_paid` checks the accounting amount → a recipient-fee token delivers less → the redeemer receives less than the specified minimum
invariant: A successful redemption must deliver at least `min_paid` collateral units to the redeemer.
violation_path: A redeemer sets `min_paid = 100` → `_redeem` calculates 100 → `_push` transfers 100 through a token that deducts 10 from the recipient.
proof: `_redeem` checks `paid >= min_paid` before `_push`; `_push` does not measure the recipient’s balance. The transaction succeeds with `paid = 100`, but the redeemer receives 90.
description: A redeemer can receive fewer collateral tokens than `min_paid` when the token charges a fee to the recipient.
fix: Check the recipient’s actual balance increase against `min_paid` before the transaction completes.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
code_smells: The function caps `repay` at `needed` and floors `seized` to collateral base units.
unverified: A deployed collateral price and position size that make the zero-seizure period materially harmful remain unverified.
description: A liquidator receives zero collateral when the calculated seizure is less than one collateral base unit.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | function_name | all-or-nothing-liquidation
code_smells: The branch below 110% requires `max_repay >= repay` and clears the position in one call.
unverified: The availability of a liquidator with enough stablecoin during a material shortfall remains unverified.
description: A liquidator needs the full repayment in one balance to close a position below 110%.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: redemption-oracle-lag-extraction | group_key: modules/cdp/cdp.vy | _redeem | redemption-oracle-lag-extraction
code_smells: The function pays collateral at the latest accepted oracle answer and charges a fee from 0.5% to 5%.
unverified: A supported feed must lag the market price by more than the applicable fee while the answer remains within `ORACLE_TIMEOUT`.
description: A redeemer can take borrower collateral at an old oracle price if the market price moves beyond the fee.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path
code_smells: The caller supplies an exact `amount`, and `_repay` rejects an amount above current debt.
unverified: The impact of transaction timing and fee settings on practical full repayment remains unverified.
description: A borrower may need to predict the execution timestamp to repay all accrued debt in one call.
