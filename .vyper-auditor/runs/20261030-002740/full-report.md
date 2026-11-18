# 🔐 Security Review — core (Vyper)

---

## Scope

|  |  |
| --- | --- |
| **Mode** | filename |
| **Files reviewed** | `modules/cdp/cdp.vy` · `modules/cdp/cdp_native.vy` · `modules/cdp/cdp_erc20.vy`<br>`modules/tokens/erc20.vy` |
| **Compiler context** | pragma version ~=0.4.3 in all four files; nonreentrancy on in cdp.vy, cdp_native.vy, cdp_erc20.vy and off in tokens/erc20.vy; no evm-version pragma; no Vyper version pinned in moccasin.toml, pyproject.toml, or uv.lock; compiled version not verified |
| **Confidence threshold (1-100)** | 75 |
| **Passes** | 2 of 3 (pass 1 ran 8/12 agents, pass 3 failed) |
| **Memory** | 31 records before this scan · 55 after · `c17c453` |

---

## Findings

[75] **1. Liquidation writes off the liquidator bonus as bad debt below par**

`modules/cdp/cdp.vy._liquidate` · Confidence: 75 · [agents: 5,7,9,12] · seen in 2/2 runs · NEW

**Description**
A liquidator of a position just below par takes about 9% of its debt as profit, and the protocol writes it off as bad debt.

**Proof**
- Code: `cdp.vy:376-385`. When `value < d * PRECISION`, the code sets `repay = value // LIQUIDATION_PENALTY` (1.1e18). It then sets `seized = c`, `written_off = d - repay`, and `self.bad_debt += written_off`. The `else` branch hands over all collateral for about `value / 1.1`.
- Setup: 1 ETH collateral (18 decimals), 1000 mUSD debt, `rate_index = 1e18`, and an 8-decimal oracle at $999.90. `PRICE_SCALE = 10**(36 - 8 - 18) = 1e10` (cdp.vy:262). So `p = 9.999e20` and `value = 9.999e38` (1e36-scaled).
- Trace: `value < d * PRECISION = 1e39`, so `repay = 9.999e38 // 1.1e18 = 909.09e18`. `seized = 1 ETH`, and `written_off = 1000 - 909.09 = 90.91 mUSD`. The true shortfall is $0.10.
- Liquidator pays 909.09 mUSD and receives 1 ETH worth $999.90, a profit of about $90.81. The 90.91 mUSD joins `bad_debt`. `cover_bad_debt` then pays reserve collateral to any mUSD holder (cdp.vy:422-432).
- Bound: at `value = d * 1e18 - 1`, the write-off is about 0.0909 * d. Par gives a write-off of zero, and one wei below par gives 9.1% of debt. That discontinuity is the defect.
- Self-liquidation: `_liquidate` has no `user != msg.sender` check (cdp.vy:348-391). A borrower can run this path on its own position, pay the reduced repay, take all collateral, and keep the mUSD it did not burn.
- Reachability: `liquidate` is public in `cdp_native.vy:93` and `cdp_erc20.vy:123`. The position must be unhealthy (`assert self._collat_ratio(user) < MIN_COLLAT_RATIO`, cdp.vy:350). A 0.1% price drop below par, or interest accrual over a few days, reaches it.
- Compiler: `# pragma version ~=0.4.3` (cdp.vy:1). The arithmetic is uint256 floor division and is not version-sensitive.

**Fix**

```diff
-            repay = value // LIQUIDATION_PENALTY
+            repay = value // PRECISION
```

The guard `value < d * PRECISION` makes `value // PRECISION < d`. So `written_off = d - repay` stays positive and equals the shortfall, up to rounding. Trade-off: a liquidator earns nothing below par, so any incentive for underwater liquidations needs a separate funding source.

---

[75] **2. Position owner moves the redemption fee by changing its ratio**

`modules/cdp/cdp.vy._redeem` · Confidence: 75 · [agents: 8,12] · seen in 2/2 runs · NEW

**Description**
A position owner changes its collateral ratio before a redemption, so the redemption fee changes and the redeemer receives less collateral.

**Proof**
- Code: `cdp.vy:406-408` reads `ratio` from the live `collateral[user]` at execution, then passes it to `_redemption_fee` (cdp.vy:575-580). That helper raises the fee from 0.5% at 150% to the cap of 5%.
- Defaults: `cdp_native.vy:106` and `cdp_erc20.vy:136` set `min_paid` to 0. A redeemer who omits it has no bound on the fee.
- Deposit variant: 1 ETH collateral, 1333.33 mUSD debt, $2000. The ratio is 1.5 and the fee is 0.5%. A redeemer burns 1000 mUSD with `min_paid = 0`, and the expected payment is 0.4975 ETH. The owner first deposits 3 ETH, so collateral becomes 4 ETH and the ratio becomes 6.0. The fee rises to 5%, and the redeemer receives `1000 * 0.95 / 2000 = 0.475 ETH`, which is 0.0225 ETH less. The owner then withdraws the 3 ETH. The ratio afterwards is about 3.15, above 1.5, so the withdraw check passes. The owner nets about $45 from the redeemer.
- Burn variant (no collateral moved): $3000 collateral and 2000 mUSD debt give a ratio of 1.5 and a fee of 0.5%. The owner burns 1000 of its own mUSD (`burn`, cdp.vy:285), so debt falls to 1000 and the ratio becomes 3.0. The fee becomes `5e15 + 1.5e16 = 2.0%`. A 100 mUSD redemption pays 98.0 USD instead of 99.5 USD. The owner then mints the 1000 mUSD back, and the ratio returns to 1.5.
- Ordering: the owner's change must land before the redeem, and in the deposit variant the withdraw must land after it. That needs block ordering or MEV builder ordering. The burn variant needs only the owner's own transactions before the redeem.
- Compiler: `# pragma version ~=0.4.3` (cdp.vy:1). Not version-sensitive.
- Trade-off: the fix removes the feature that a riskier position costs more to redeem, which the `_redeem` docstring describes (cdp.vy:396-399).

**Fix**

```diff
-    paid: uint256 = amount * (PRECISION - self._redemption_fee(ratio)) // self._price()
+    paid: uint256 = amount * (PRECISION - REDEMPTION_FEE) // self._price()
```

`ratio` still feeds the health check on the line above, so the function still compiles and checks health. The fee is now fixed, so neither a deposit nor a burn can move it.

---

Findings List

| # | Confidence | Title |
|---|---|---|
| 1 | [75] | Liquidation writes off the liquidator bonus as bad debt below par |
| 2 | [75] | Position owner moves the redemption fee by changing its ratio |

---

## Leads

_Vulnerability trails with concrete code smells where the full exploit path could not be completed in one analysis pass. These are not false positives — they are high-signal leads for manual review. Not scored._

- **Collateral credit follows any balance increase during transferFrom** — `modules/cdp/cdp_erc20.vy._pull` · seen in 2/2 runs · NEW · [agents: 2] — Code smells: `_pull` returns the whole balance change across `transferFrom` (cdp_erc20.vy:165-168), and `deposit` credits that amount to `msg.sender`. Unverified: a collateral token that adds to this contract's balance during `transferFrom`, such as a rebasing or hook-funded inflow.
- **The module measures inflows but trusts outflows** — `modules/cdp/cdp_erc20.vy._push` · seen in 2/2 runs · NEW · [agents: 6] — Code smells: `_push` sends `amount` and never reads `balanceOf(self)` (cdp_erc20.vy:173-174), while `_pull` measures the inflow (cdp_erc20.vy:165-168). A token that charges its sender above `amount` leaves the contract short, so late withdrawals revert. Unverified: whether a sender-fee collateral token reaches a deployed `cdp_erc20`.
- **A paused collateral token makes every liquidation revert** — `modules/cdp/cdp_erc20.vy.liquidate` · seen in 1/2 runs · NEW · [agents: 6] — Code smells: `liquidate` pushes `seized` through `_push`, which asserts the token transfer result (cdp_erc20.vy:173-174). A paused collateral token therefore reverts the whole liquidation. Unverified: whether a pausable collateral token is deployed with `cdp_erc20`.
- **A token that rejects zero transfers makes liquidation revert when nothing is seized** — `modules/cdp/cdp_erc20.vy.liquidate` · seen in 1/2 runs · NEW · [agents: 6] — Code smells: `liquidate` pushes `seized` even when it rounds to zero, and `_push` then calls `transfer` with 0 (cdp_erc20.vy:173-174). Unverified: whether the deployed collateral token rejects zero-value transfers.
- **Redeem checks min_paid before the recipient's token fee** — `modules/cdp/cdp_erc20.vy.redeem` · seen in 2/2 runs · NEW · [agents: 6] — Code smells: `_redeem` asserts `paid >= min_paid` on the gross amount (cdp.vy:409), and `redeem` then pushes `paid` (cdp_erc20.vy:137). A recipient-fee token delivers less than `min_paid`. Unverified: whether a deployed `cdp_erc20` uses a fee token.
- **The ERC-20 redeem also defaults min_paid to zero** — `modules/cdp/cdp_erc20.vy.redeem` · seen in 1/2 runs · NEW · [agents: 8] — Code smells: `cdp_erc20.vy:136` declares the same zero default as `cdp_native.vy:106`. Unverified: whether a deployed `cdp_erc20` host exists and whether its callers pass `min_paid`.
- **Redeem defaults min_paid to zero, so no slippage bound applies** — `modules/cdp/cdp_native.vy.redeem` · seen in 2/2 runs · NEW · [agents: 8] — Code smells: `cdp_native.vy:106` declares `min_paid: uint256 = 0`, so an omitted bound accepts any fee. The redemption-fee finding above then has no bound. Unverified: whether front-ends always pass `min_paid`.
- **Any caller compounds the stability fee by triggering accrual** — `modules/cdp/cdp.vy._accrue` · seen in 2/2 runs · NEW · [agents: 1,10] — Code smells: the stored index compounds on every call (cdp.vy:459-461), and `_rate_index` applies one linear step per gap (cdp.vy:499). Growth therefore depends on call frequency: one accrual a year gives 10.00%, and per-second accrual gives about 10.52%. Unverified: whether the 10% cap is nominal or effective, since the comment at cdp.vy:145 says growth happens every second, and whether any caller gains beyond the extra interest, which goes to surplus.
- **Collateral paid for surplus stays locked until bad debt appears** — `modules/cdp/cdp.vy._buy_surplus` · seen in 1/2 runs · NEW · [agents: 3] — Code smells: `_buy_surplus` adds the paid collateral to `reserve` (cdp.vy:446), and only `_cover_bad_debt` reduces it (cdp.vy:429). Unverified: whether a withdrawal path exists outside the in-scope files. None exists in the modules.
- **Donated mUSD is sold while bad debt stands unsettled** — `modules/cdp/cdp.vy._buy_surplus` · seen in 1/2 runs · NEW · [agents: 5] — Code smells: `_settle` runs only from `_accrue` when it mints a fee (cdp.vy:465-466) and inside liquidation (cdp.vy:390). mUSD sent straight to the contract raises `balanceOf[self]` while `bad_debt` stays open, and `_buy_surplus` sells that balance (cdp.vy:445). Unverified: whether any holder loses from the unsettled bad debt. The desync is shown, but no loss path is.
- **Surplus purchases use the oracle price with one fixed fee** — `modules/cdp/cdp.vy._buy_surplus` · seen in 2/2 runs · NEW · [agents: 3,7,12] — Code smells: `bought` prices surplus at the oracle and subtracts only the fixed `SWAP_FEE` (cdp.vy:443), so a buyer gains when the oracle reads more than 0.5% above market. Unverified: the deviation thresholds of the deployed feeds. The Base ETH/USD feed records 0.15% deviation, which the fee covers. Held at lead, as in pass 1: no verified safe fix exists without those thresholds.
- **Cover of bad debt pays reserve collateral at the oracle price** — `modules/cdp/cdp.vy._cover_bad_debt` · seen in 2/2 runs · NEW · [agents: 7,9,12] — Code smells: `paid` prices the reserve payout at the oracle with the same fixed `SWAP_FEE` (cdp.vy:426), so a caller gains reserve collateral when the oracle reads below market by more than 0.5%. Unverified: the deviation thresholds of the deployed feeds, as for the swap lead.
- **Constructor never checks mUSD decimals** — `modules/cdp/cdp.vy.__init__` · seen in 2/2 runs · NEW · [agents: 1] — Code smells: `__init__` checks collateral and oracle decimals (cdp.vy:253-262) but never reads the mUSD decimals. `_collat_ratio`, `_redeem`, `_cover_bad_debt`, and `_buy_surplus` assume 1e18 raw units per dollar. Unverified: whether a deployed mUSD uses decimals other than 18.
- **Liquidation seizes more collateral when the oracle reads low** — `modules/cdp/cdp.vy._liquidate` · seen in 1/2 runs · NEW · [agents: 7,10] — Code smells: one oracle answer decides the health test (cdp.vy:351) and the seizure (cdp.vy:373). A stale low answer can make a healthy position look liquidatable and seize more than the 110% bonus. Unverified: the size of lag needed, and whether the answer stays within `ORACLE_TIMEOUT`.
- **Liquidation writes off debt on positions that cover it by 2 wei** — `modules/cdp/cdp.vy._liquidate` · seen in 1/2 runs · NEW · [agents: 1] — Code smells: the health branch compares `value`, which floors the collateral USD value (cdp.vy:356), with `d`, which `_debt` rounds up (cdp.vy:514-515). A position whose collateral covers its debt by under 2 wei takes the else branch and writes off about 9% of its debt. Unverified: whether a real position can reach that 2-wei window together with a price and an index. The same fix as the underwater finding removes this path.
- **The price read accepts answers at the aggregator floor** — `modules/cdp/cdp.vy._price` · seen in 2/2 runs · NEW · [agents: 3,11] — Code smells: `_price` asserts only `answer > 0` (cdp.vy:533) and never compares the answer with the aggregator's minimum or maximum. A clamped answer overstates collateral in `mint`. Unverified: the minimum answer of each deployed feed, which the repo does not record.
- **Oracle decimals are frozen at deployment** — `modules/cdp/cdp.vy._price` · seen in 2/2 runs · NEW · [agents: 1,11] — Code smells: `_price` multiplies the answer by the immutable `PRICE_SCALE` (cdp.vy:535) and never reads the feed's decimals again after `__init__` (cdp.vy:258-262). Unverified: whether the `ORACLE` address, if it is a proxy, can later point to an aggregator with different decimals.
- **A retired feed makes every price-based function fail** — `modules/cdp/cdp.vy._price` · seen in 1/2 runs · NEW · [agents: 3] — Code smells: `ORACLE` is immutable, and `_price` has no fallback feed. A failed read or a stale answer reverts every price-based call, including liquidation and redemption (cdp.vy:523-535). Unverified: whether a deployed feed is retired or paused.
- **Redemption pays collateral at the oracle price** — `modules/cdp/cdp.vy._redeem` · seen in 2/2 runs · NEW · [agents: 3,7,10] — Code smells: `paid` divides by `self._price()` (cdp.vy:408), and the redemption fee is the only buffer. A redeemer takes borrower collateral worth more than the mUSD burned when the oracle reads below market. Unverified: the feed lag at redemption time against the 0.5% fee.
- **An oracle outage blocks withdrawals for borrowers with debt** — `modules/cdp/cdp.vy._withdraw` · seen in 1/2 runs · NEW · [agents: 3] — Code smells: `_withdraw` checks the ratio through `_collat_ratio`, which reads `_price` whenever debt is non-zero (cdp.vy:560-566). An outage or sequencer grace period therefore blocks withdrawals for borrowers with debt. Unverified: the outage length, and whether a borrower can clear its debt with `burn` first.
- **A burn sized to an earlier debt leaves dust after interest accrues** — `modules/cdp/cdp.vy.burn` · seen in 1/2 runs · NEW · [agents: 3] — Code smells: `_repay` rejects an amount above the current debt (cdp.vy:485), and debt grows every second through `_rate_index`, so a burn sized to an earlier debt leaves dust. Unverified: whether a borrower can predict the block timestamp to close the position in one burn.
- **Any caller opens a position too small to liquidate profitably** — `modules/cdp/cdp.vy.mint` · seen in 1/2 runs · NEW · [agents: 3] — Code smells: `mint` sets no lower bound on the amount, and `_liquidate` seizes nothing for dust repays (cdp.vy:373). Unverified: whether a dust position costs a liquidator more gas than the bonus. A one-wei debt passes the ratio check when collateral is deposited.

---

## Known from earlier scans

_Recorded by earlier scans of this repo, not raised again by this one. Not re-checked — a record here may be fixed, or may still be live and missed. `.vyper-auditor/memory.tsv`._

| Scans | Kind | Location | Title |
|---|---|---|---|
| 1 | LEAD | `modules-cdp-erc20-vy.-push` | The module measures inflows but trusts outflows |
| 1 | LEAD | `modules-cdp-erc20-vy.liquidate` | A paused collateral token makes every liquidation fail |
| 1 | LEAD | `modules-cdp-erc20-vy.liquidate` | A token that rejects zero transfers makes liquidation revert when nothing is sei |
| 1 | LEAD | `modules-cdp-vy.-accrue` | Any caller compounds interest with mint(0) |
| 1 | LEAD | `modules-cdp-vy.-buy-surplus` | Buyers cannot buy a surplus residue smaller than one collateral unit |
| 1 | LEAD | `modules-cdp-vy.-buy-surplus` | No account can withdraw the reserve unless bad debt appears |
| 1 | FINDING | `modules-cdp-vy.-buy-surplus` | Buyers take the oracle lag from the surplus |
| 1 | FINDING | `modules-cdp-vy.-cover-bad-debt` | Callers take reserve collateral at the oracle lag |
| 1 | LEAD | `modules-cdp-vy.-liquidate` | Underwater liquidation needs the full repay from one balance |
| 1 | FINDING | `modules-cdp-vy.-liquidate` | Liquidators receive zero collateral for coarse high-price collateral |
| 1 | FINDING | `modules-cdp-vy.-liquidate` | Liquidation books bad debt on positions that cover their debt |
| 1 | LEAD | `modules-cdp-vy.-price` | The price read accepts answers at the aggregator floor |
| 1 | LEAD | `modules-cdp-vy.-price` | A retired feed makes every price-based function fail forever |
| 1 | LEAD | `modules-cdp-vy.-rate-index` | Callers can make the stability fee compound every block |
| 1 | LEAD | `modules-cdp-vy.-redeem` | Redeemers take borrower collateral when the oracle lag exceeds the fee |
| 1 | LEAD | `modules-cdp-vy.-withdraw` | An oracle outage locks surplus collateral for every borrower with debt |
| 1 | LEAD | `modules-cdp-vy.burn` | Borrowers cannot close a position unless the burn lands in the predicted second |
| 1 | LEAD | `modules-cdp-vy.mint` | Borrowers can open positions too small to liquidate at a profit |
| 1 | LEAD | `src-ministable-vy.-init-` | The Arbitrum oracle timeout may be shorter than the feed heartbeat |
| 1 | LEAD | `src-ministable-vy.-init-` | The constructor accepts mUSD decimals other than 18 |
| 1 | LEAD | `src-ministable-vy.-init-` | The only deploy script binds the immutable oracle to a mock that any caller can  |
| 1 | LEAD | `src-ministable-vy.-price` | The price read does not reject answers at the aggregator min/max bounds |
| 1 | LEAD | `src-ministable-vy.-price` | The price scaling assumes an 8-decimal feed |
| 1 | LEAD | `src-ministable-vy.-price` | A retired or paused feed blocks liquidation permanently |
| 1 | LEAD | `src-ministable-vy.-price` | The price read has no L2 sequencer uptime check |
| 1 | LEAD | `src-ministable-vy.-price` | The oracle timeout equals the feed heartbeat and has no margin |
| 1 | LEAD | `src-ministable-vy.liquidate` | Liquidation needs the caller to hold the whole debt in one balance |
| 1 | LEAD | `src-ministable-vy.liquidate` | A borrower at the mint limit loses all surplus ETH after a 1e-8 USD price tick |
| 1 | FINDING | `src-ministable-vy.liquidate` | No liquidator closes a position whose collateral is worth less than its debt |
| 1 | LEAD | `src-ministable-vy.mint` | Borrowers can open positions too small to liquidate at a profit |
| 1 | LEAD | `src-ministable-vy.withdraw` | An oracle outage locks surplus ETH for every borrower with debt |

---

> ⚠️ This review was performed by an AI assistant. AI analysis can never verify the complete absence of vulnerabilities and no guarantee of security is given. Team security reviews, bug bounty programs, and on-chain monitoring are strongly recommended. For a consultation regarding your projects' security, visit [https://www.pashov.com](https://www.pashov.com)
