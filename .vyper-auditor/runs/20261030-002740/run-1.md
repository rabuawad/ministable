<!--RUN pass=1 agents=8/12-->

Completeness: 14 unique (file, function) in raw, 11 covered in final, 3 rejected with reasons.

Lost coverage: four launched specialties returned no structured output. One agent was stopped by a user interrupt. Three ended on the API rate limit or mid-task before writing any blocks. The specialty numbers of the lost agents were not recorded at launch, so the most likely specialties are 4 (execution trace), 9 (boundary), 10 (numerical gap), and 11 (trust gap). Their coverage is absent from this pass. The `agents=` attributions below are inferred from each returned agent's content, because launch IDs were not mapped to specialty numbers.

Scope: named scan of `modules/cdp/cdp.vy`, `modules/cdp/cdp_native.vy`, `modules/cdp/cdp_erc20.vy`, and `modules/tokens/erc20.vy`. The host `src/ministable.vy` was read as context only. Its candidates (an unlocked exported `transferFrom` path, a transient-lock chain requirement, and a host export gap) are outside named scope and are excluded.

Rejected with reasons:
- `surplus` in `modules/cdp/cdp.vy`: the view omits pending interest. No in-repo consumer exists, and no victim is shown. Informational only.
- `_liquidate` dust zero-seize: a repay below one collateral unit seizes zero. The only loss falls on the liquidator's own mUSD burn, so the harm is self-harm. The earlier-scan FINDING `coarse-collateral-zero-seize` is not re-found here.
- `_liquidate` full-debt band: positions between 100% and 110% require the full debt in one repay. This is the designed behavior (cdp.vy:341-344), not a bug.
- `_liquidate` self-liquidation bad-debt claim: any mUSD holder may cover bad debt by design (cdp.vy:422-432). The extra payout comes from the underwater write-off below, so it is folded into that finding.

Demoted to leads: the oracle-spread gap in `_buy_surplus` and `_cover_bad_debt`. The Base ETH/USD feed records 0.15% deviation (`moccasin.toml`), which the 0.5% `SWAP_FEE` covers. The Sonic and Monad feed deviations are not recorded in the repo.

Compiler context: `# pragma version ~=0.4.3` in all four files. No version-sensitive claim appears in the findings below; all rely on uint256 arithmetic and call ordering.

<!--F key=modules-cdp-cdp-vy|-liquidate|underwater-bonus-bad-debt conf=75 kind=FINDING agents=3,5,7,12-->

[75] **Liquidation writes off the liquidator bonus as bad debt below par**

`modules/cdp/cdp.vy._liquidate` · Confidence: 75

**Description**
A liquidator of a position just below par takes about 9% of its debt as profit, and the protocol writes it off as bad debt.

**Proof**
- Code: `cdp.vy:376-385`. When `value < d * PRECISION`, the code sets `repay = value // LIQUIDATION_PENALTY` (1.1e18). It then sets `seized = c`, `written_off = d - repay`, and `self.bad_debt += written_off`. The `else` branch hands over all collateral for about `value / 1.1`.
- Setup: 1 ETH collateral (18 decimals), 1000 mUSD debt, `rate_index = 1e18`, and an 8-decimal oracle at $999.90. `PRICE_SCALE = 10**(36 - 8 - 18) = 1e10` (cdp.vy:262). So `p = 9.999e20` and `value = 9.999e38` (1e36-scaled).
- Trace: `value < d * PRECISION = 1e39`, so `repay = 9.999e38 // 1.1e18 = 909.09e18`. `seized = 1 ETH`, and `written_off = 1000 - 909.09 = 90.91 mUSD`. The true shortfall is $0.10.
- Liquidator pays 909.09 mUSD and receives 1 ETH worth $999.90, a profit of about $90.81. The 90.91 mUSD joins `bad_debt`. `cover_bad_debt` then pays reserve collateral to any mUSD holder (cdp.vy:422-432).
- Bound: at `value = d * 1e18 - 1`, the write-off is about 0.0909 * d. Par gives a write-off of zero, and one wei below par gives 9.1% of debt. That discontinuity is the defect.
- Reachability: `liquidate` is public in `cdp_native.vy:93` and `cdp_erc20.vy:123`. The position must be unhealthy (`assert self._collat_ratio(user) < MIN_COLLAT_RATIO`, cdp.vy:350). A 0.1% price drop below par, or interest accrual over a few days, reaches it.
- Compiler: `# pragma version ~=0.4.3` (cdp.vy:1). The arithmetic is uint256 floor division and is not version-sensitive.

**Fix**

```diff
-            repay = value // LIQUIDATION_PENALTY
+            repay = value // PRECISION
```

The guard `value < d * PRECISION` makes `value // PRECISION < d`. So `written_off = d - repay` stays positive and equals the shortfall, up to rounding. Trade-off: a liquidator earns nothing below par, so any incentive for underwater liquidations needs a separate funding source.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-redeem|redemption-fee-ratio-spoof conf=75 kind=FINDING agents=8,12-->

[75] **Position owner raises the redemption fee with a temporary deposit**

`modules/cdp/cdp.vy._redeem` · Confidence: 75

**Description**
A position owner deposits collateral before a redemption, so the redemption fee rises and the redeemer receives less collateral.

**Proof**
- Code: `cdp.vy:406-408` reads `ratio` from the live `collateral[user]` at execution, then passes it to `_redemption_fee` (cdp.vy:575-580). That helper raises the fee from 0.5% at 150% to the cap of 5%.
- Defaults: `cdp_native.vy:106` and `cdp_erc20.vy:136` set `min_paid` to 0. A redeemer who omits it has no bound on the fee.
- Replay: 1 ETH collateral, 1333.33 mUSD debt, $2000. The ratio is 1.5 and the fee is 0.5%. A redeemer burns 1000 mUSD with `min_paid = 0`. The expected payment is 0.4975 ETH.
- The owner first deposits 3 ETH. Collateral becomes 4 ETH and the ratio becomes 6.0, so the fee rises to 5%. The redeemer receives `1000 * 0.95 / 2000 = 0.475 ETH`, which is 0.0225 ETH less. The owner's retained fee is 0.025 ETH, not 0.0025 ETH.
- The owner then withdraws the 3 ETH. The ratio afterwards is about 3.15, above 1.5, so the withdraw check passes. The owner nets about 0.0225 ETH (about $45) from the redeemer.
- Ordering: the owner's deposit must land before the redeem, and the withdraw after it. That needs block ordering or MEV builder ordering.
- Compiler: `# pragma version ~=0.4.3` (cdp.vy:1). Not version-sensitive.
- Trade-off: the fix removes the feature that a riskier position costs more to redeem, which the `_redeem` docstring describes (cdp.vy:396-399).

**Fix**

```diff
-    paid: uint256 = amount * (PRECISION - self._redemption_fee(ratio)) // self._price()
+    paid: uint256 = amount * (PRECISION - REDEMPTION_FEE) // self._price()
```

`ratio` still feeds the health check on the line above, so the function still compiles and checks health. The fee is now fixed, so a deposit cannot move it.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-accrue|caller-driven-compounding kind=LEAD agents=1,12-->

- **Any caller compounds the stability fee by triggering accrual** — `modules/cdp/cdp.vy._accrue` — Code smells: the stored index compounds on every call (cdp.vy:459-461 and cdp.vy:499). The effective annual rate therefore follows call frequency: a 10% nominal rate gives about 10.52% a year at frequent calls. Unverified: whether the 10% cap is nominal or effective, and whether any caller gains beyond the extra interest, which goes to surplus.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-init-|unchecked-stablecoin-decimals kind=LEAD agents=1-->

- **Constructor never checks mUSD decimals** — `modules/cdp/cdp.vy.__init__` — Code smells: `__init__` checks collateral and oracle decimals (cdp.vy:253-262) but never reads the mUSD decimals. `_collat_ratio`, `_redeem`, `_cover_bad_debt`, and `_buy_surplus` assume 1e18 raw units per dollar. Unverified: whether a deployed mUSD uses decimals other than 18.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-price|frozen-oracle-decimals kind=LEAD agents=1-->

- **Oracle decimals are frozen at deployment** — `modules/cdp/cdp.vy._price` — Code smells: `_price` multiplies the answer by the immutable `PRICE_SCALE` (cdp.vy:535) and never reads the feed's decimals again after `__init__` (cdp.vy:258-262). Unverified: whether the `ORACLE` address, if it is a proxy, can later point to an aggregator with different decimals.

<!--/F-->

<!--F key=modules-cdp-cdp-erc20-vy|-pull|balance-delta-credit kind=LEAD agents=2-->

- **Collateral credit follows any balance increase during transferFrom** — `modules/cdp/cdp_erc20.vy._pull` — Code smells: `_pull` returns the whole balance change across `transferFrom` (cdp_erc20.vy:165-168), and `deposit` credits that amount to `msg.sender`. Unverified: a collateral token that adds to this contract's balance during `transferFrom`, such as a reflection or hook-funded inflow.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-buy-surplus|zero-fee-oracle-swap kind=LEAD agents=3,7-->

- **Surplus purchases use the oracle price with one fixed fee** — `modules/cdp/cdp.vy._buy_surplus` — Code smells: `bought` uses the oracle answer and one fixed `SWAP_FEE` (cdp.vy:443), so a buyer keeps the gap when the oracle reads more than 0.5% above market. Unverified: the deviation thresholds of the Sonic S/USD and Monad MON/USD feeds. The Base ETH/USD feed records 0.15% deviation, which the fee covers.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-cover-bad-debt|zero-fee-oracle-swap kind=LEAD agents=7-->

- **Cover of bad debt pays reserve collateral at the oracle price** — `modules/cdp/cdp.vy._cover_bad_debt` — Code smells: `paid` uses the oracle answer and the same fixed `SWAP_FEE` (cdp.vy:426), so a caller takes reserve collateral worth more than the mUSD burned when the oracle reads below market. Unverified: the feed deviation, as for `_buy_surplus`.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-redeem|redemption-oracle-lag-extraction kind=LEAD agents=3,7-->

- **Redemption pays collateral at the oracle price** — `modules/cdp/cdp.vy._redeem` — Code smells: `paid` divides by `self._price()` (cdp.vy:408), and the redemption fee is the only buffer. A redeemer takes borrower collateral worth more than the mUSD burned when the oracle reads below market. Unverified: the feed lag at redemption time, and whether it exceeds the fee (0.5% at 150%).

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-price|chainlink-min-answer-clamp kind=LEAD agents=3-->

- **The price read accepts answers at the aggregator floor** — `modules/cdp/cdp.vy._price` — Code smells: `_price` asserts only `answer > 0` (cdp.vy:533) and never compares the answer with the aggregator's `minAnswer`. A clamped answer overstates collateral in `mint`. Unverified: the `minAnswer` of each deployed feed, which the repo does not record.

<!--/F-->

<!--F key=modules-cdp-cdp-erc20-vy|-push|fee-on-transfer-outflow kind=LEAD agents=6-->

- **The module measures inflows but trusts outflows** — `modules/cdp/cdp_erc20.vy._push` — Code smells: `_push` calls `COLLATERAL.transfer` and never reads `balanceOf(self)` (cdp_erc20.vy:173-174), while `_pull` measures the inflow (cdp_erc20.vy:165-168). A token that debits the sender above `amount` leaves the last withdrawer's transfer short. Unverified: whether a sender-fee collateral token reaches a deployed `cdp_erc20` host.

<!--/F-->

<!--F key=modules-cdp-cdp-erc20-vy|redeem|min-paid-gross-amount kind=LEAD agents=6-->

- **Redeem checks min_paid before the recipient's token fee** — `modules/cdp/cdp_erc20.vy.redeem` — Code smells: `_redeem` asserts `paid >= min_paid` on the protocol amount (cdp.vy:409), then `_push` sends it (cdp_erc20.vy:136-137). A recipient-fee token therefore delivers less than `min_paid`. Unverified: whether `min_paid` should bound the net receipt, and whether a deployed `cdp_erc20` uses a recipient-fee token.

<!--/F-->

<!--F key=modules-cdp-cdp-native-vy|redeem|unset-slippage-default kind=LEAD agents=8-->

- **Redeem defaults min_paid to zero, so no slippage bound applies** — `modules/cdp/cdp_native.vy.redeem` — Code smells: `cdp_native.vy:106` declares `min_paid: uint256 = 0`, so a caller who omits it accepts any fee, and the redemption-fee finding above has no bound. `cdp_erc20.vy:136` has the same default. Unverified: whether front-ends and integrators always pass a non-zero `min_paid`.

<!--/F-->
