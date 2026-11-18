[Feynman: modules/cdp/cdp.vy] The module tracks collateral and debt, calculates interest, and settles liquidations. Its accounting assumes that share and collateral-unit rounding preserve useful incentives.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens for the CDP engine. Its accounting assumes that the token’s transfer behavior matches the measured amounts.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin for the CDP engine. Its payment paths depend on the recipient accepting the call.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances, allowances, and signatures. Its unchecked balance operations depend on the supply and balance invariants.

[Socratic: modules/cdp/cdp.vy:_liquidate — why?] What gives a liquidator an incentive when the required repayment buys less than one collateral base unit?

[Inversion: _liquidate] A liquidator can choose a small `max_repay`; a borrower can have coarse collateral; a price change can leave a position just below 150%.

[Inversion: _accrue] A caller can invoke `mint(0)` repeatedly; debt can be split among positions; the aggregate fee can fall below one stablecoin base unit.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: coarse-collateral-zero-seize | group_key: modules/cdp/cdp.vy | _liquidate | coarse-collateral-zero-seize
seam: boundary×precision
code_smells: The function caps `repay` at the amount needed to restore the ratio, then rounds `seized` down to collateral base units.
unverified: The deployed collateral price and decimals must make the zero-seizure interval economically material.
proof: With 6-decimal collateral, an oracle price of $990 billion per token, 15 collateral base units, and $10 million debt, collateral is worth $14.85 million. The required repayment is approximately $375,000, but `seized = repay * 1.1e18 // p` is zero because one collateral base unit is worth $990,000.
description: A liquidator receives no collateral when the required repayment rounds below one collateral base unit.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
seam: boundary×invariant
code_smells: The branch below 110% requires `max_repay >= repay` and clears all debt shares in one call.
unverified: The available liquidator balances and liquidity must be insufficient for a material position.
proof: For $100 million debt and $105 million collateral, the branch requires one caller to burn $100 million; a caller with $99 million cannot reduce the position.
description: A large position can remain open when no liquidator holds the required stablecoin balance.
