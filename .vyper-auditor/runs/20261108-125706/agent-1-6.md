[Feynman: cdp_erc20] The wrapper takes collateral and sends it back after the CDP module changes its records. The token defines how much leaves the wrapper.

[Inversion: _push] A caller can withdraw after another user deposits, select a token with a sender fee, or receive fewer tokens than the requested amount.

[Feynman: cdp_native] The wrapper receives native coin and sends it after the CDP module changes its records. The caller must accept the native coin.

[Feynman: erc20] The module tracks stablecoin balances and approvals. The host chooses its decimal metadata and exports its functions.

[Feynman: cdp] The module converts collateral and oracle values into debt, liquidation, redemption, and reserve records. The calculations assume specific units and token behavior.

[Socratic: modules/cdp/cdp.vy — _accrue] Why does each caller choose when the contract adds the elapsed fee to the index?

[Inversion: _accrue] A caller can invoke `mint(0)`, invoke it after each block, or leave the index untouched for a year.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow  
code_smells: The wrapper credits actual inflows but records the requested outflow without checking the token balance.  
unverified: Whether a deployed collateral token charges the sender more than the requested transfer amount, or charges recipients a material fee. With a 10% sender surcharge, two 100-token deposits leave 200 tokens; one 100-token withdrawal removes 110 and leaves only 90 for the other user.  
description: A token with a sender surcharge can make one withdrawal consume collateral that belongs to another user.

LEAD | contract: modules/cdp/cdp.vy | function: _accrue | bug_class: caller-driven-compounding | group_key: modules/cdp/cdp.vy | _accrue | caller-driven-compounding  
code_smells: The function applies elapsed interest to the current index and accepts calls through `mint(0)`.  
unverified: Whether the intended fee permits callers to choose its compounding frequency. At an approximate 10% annual rate, one annual update gives approximately 1.10 times the index, while frequent updates approach approximately 1.10517.  
description: Any caller can increase borrower debt through frequent index updates if the intended fee uses simple interest.

LEAD | contract: modules/cdp/cdp.vy | function: burn | bug_class: no-full-repay-path | group_key: modules/cdp/cdp.vy | burn | no-full-repay-path  
code_smells: The function accepts a fixed amount, and `_repay` rejects an amount above the debt at execution.  
unverified: Whether borrowers can reliably predict the execution timestamp or use another available transaction path to close a position when interest accrues.  
description: A borrower can leave residual debt when the execution timestamp differs from the timestamp used to calculate repayment.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: chainlink-min-answer-clamp | group_key: modules/cdp/cdp.vy | _price | chainlink-min-answer-clamp  
code_smells: The function accepts every positive, recent oracle answer without a feed-specific lower bound.  
unverified: Whether the selected deployed feed clamps its answer above a reachable market price.  
description: An oracle floor can let borrowers receive excess stablecoin if the market price falls below that floor.

LEAD | contract: modules/cdp/cdp.vy | function: _price | bug_class: immutable-oracle-no-fallback | group_key: modules/cdp/cdp.vy | _price | immutable-oracle-no-fallback  
code_smells: The constructor fixes `ORACLE`, and price-dependent operations require its successful response.  
unverified: Whether the selected feed can retire or stop updates without an independent migration path for positions.  
description: A retired oracle can block price-dependent actions if users have no position migration path.
