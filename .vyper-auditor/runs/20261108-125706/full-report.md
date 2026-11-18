# 🔐 Security Review — core (Vyper)

---

## Scope

|  |  |
| --- | --- |
| **Mode** | filename |
| **Files reviewed** | `modules/cdp/cdp.vy` · `modules/cdp/cdp_erc20.vy` · `modules/cdp/cdp_native.vy`<br>`modules/tokens/erc20.vy` |
| **Compiler context** | All four modules require ~=0.4.3. Nonreentrancy on: cdp.vy, cdp_native.vy, cdp_erc20.vy; off: erc20.vy. src/ministable.vy and ERC20 harness bind and export the modules. moccasin.toml and pyproject.toml do not pin compiler, optimizer, or EVM settings. Local .venv cannot import vyper. Deployed compiler and build settings not verified. |
| **Confidence threshold (1-100)** | 75 |
| **Passes** | 3 (pass 2 ran 9/12 agents) |
| **Memory** | 31 records before this scan · 50 after · `ab6e0c3` |

---

## Findings

[90] **1. A sender fee consumes other users' collateral**

`modules/cdp/cdp_erc20.vy._push` · Confidence: 90 · [agents: 1,2,3,4,5,6,7,8,9,10,11,12] · seen in 3/3 runs · NEW

**Description**
A caller withdraws through a sender-fee token, so the contract loses collateral that belongs to other depositors.

**Proof**
The module explicitly supports transfer-fee collateral at `modules/cdp/cdp_erc20.vy:12-18`. Its constructor checks decimals and self-collateral, but imposes no sender-fee restriction (`:87-99`). A compatible host exposes `withdraw`, which calls `cdp._withdraw(msg.sender, amount)` and then `_push(msg.sender, amount)` (`:114-116`). The ERC20 harness in `tests/mocks/cdp_erc20_harness.vy` demonstrates the module binding and export route.

`cdp._withdraw` subtracts only `amount` from the caller's collateral (`modules/cdp/cdp.vy:327-330`). A debt-free depositor passes the ratio check without an oracle read (`:560-563`). `_push` asserts only the transfer's return value (`modules/cdp/cdp_erc20.vy:173-174`). It never checks the contract's balance change. The nonreentrancy pragma and asserted boolean do not constrain the token's fee.

Alice and Bob each receive 100 collateral credits from measured deposits. A sender-surcharge token can receive each deposit in full while charging its sender separately. Their contract then holds 200 tokens. Alice withdraws 100; a 10% sender surcharge removes 110 from the contract. Bob retains a claim of 100, but only 90 tokens remain. His full withdrawal fails. The same payout helper is called by `liquidate` (`:127`), `redeem` (`:138`), and `cover_bad_debt` (`:148`). No privileged update or reentrancy is required.

Recipient-fee behavior is a different mechanism: an asserted transfer can also deliver less than its nominal amount. The companion `modules/cdp/cdp_erc20.vy.redeem` finding preserves that trace and its separate recipient-minimum fix.

**Fix**
The module should reject any outgoing transfer that reduces its balance by more than the accounted amount.

An exact-debit check is the stricter alternative suggested by specialty 5: reject outgoing transfers unless the contract's token balance decreases by exactly `amount`. Both policies stop the demonstrated extra debit; preserve the existing asserted `extcall` and `default_return_value=True`. Apply the chosen check in `_push` so all four payout callers receive it.

---

[90] **2. A transfer fee bypasses the redeemer's minimum**

`modules/cdp/cdp_erc20.vy.redeem` · Confidence: 90 · [agents: 1,2,3,4,5,6,7,8,9,10,11,12] · seen in 3/3 runs · NEW

**Description**
A redeemer receives less collateral than `min_paid` because the wrapper checks the nominal transfer amount before the token deducts its fee.

**Proof**
The wrapper advertises transfer-fee support (`modules/cdp/cdp_erc20.vy:12-16`) and promises a minimum collateral payout (`:131-139`). It obtains nominal `paid` from `cdp._redeem`, sends that amount through `_push`, then returns the nominal amount. The core checks `paid >= min_paid` before the transfer (`modules/cdp/cdp.vy:403-414`). `_push` asserts a successful token call but measures no recipient balance (`modules/cdp/cdp_erc20.vy:173-174`).

Use six-decimal collateral at $1, a healthy position with 200 tokens and 100 mUSD debt, and a redeemer with 50 mUSD. At a 200% ratio the redemption fee is 1%: 0.5% plus 1% times the 50% excess ratio. The nominal payout is 49,500,000 base units. Set `min_paid = 49,500,000`. The core passes that check and burns 50 mUSD. A token with a 1% recipient fee returns true but delivers only 49,005,000 base units. The transaction succeeds and returns 49,500,000. The actual receipt falls below the explicit minimum by 495,000 base units; the loss scales with redemption size.

The healthy-position and debt bounds permit this example. No caller access check or nonreentrancy guard checks the actual receipt. This is a supported-token compatibility path, not a claim that a currently deployed token charges that fee. Its root payment helper is `_push`; this block retains the separately reported wrapper location and net-output invariant.

**Fix**
The wrapper should check the recipient's balance increase against `min_paid` after the transfer.

Read the recipient's balance before the payout, then enforce the minimum against the increase after it. Preserve the asserted transfer result and no-return-token policy. A failure must revert the whole redemption, including its debt reduction and stablecoin burn. The sender-debit check in the companion `_push` finding does not replace this recipient check. Rejecting all fee-charging collateral is an alternative policy, but would remove the module's advertised compatibility.

---

Findings List

| # | Confidence | Title |
|---|---|---|
| 1 | [90] | A sender fee consumes other users' collateral |
| 2 | [90] | A transfer fee bypasses the redeemer's minimum |

---

## Leads

_Vulnerability trails with concrete code smells where the full exploit path could not be completed in one analysis pass. These are not false positives — they are high-signal leads for manual review. Not scored._

- **A token can reject a zero collateral payout** — `modules/cdp/cdp_erc20.vy.liquidate` · seen in 3/3 runs · NEW · [agents: 1,2,3,4,6,7,9,12] — Code smells: The wrapper calls _push even when seized is zero. — Unverified: A supported token that rejects zero transfers and a material liquidation that must take this path; arbitrary small max_repay alone shows no harm.
- **Callers choose the frequency of interest updates** — `modules/cdp/cdp.vy._accrue` · seen in 3/3 runs · NEW · [agents: 1,5,6,9] — Code smells: The index compounds each elapsed interval and mint(0) triggers accrual. — Unverified: Whether the intended fee convention differs from this index model; compare documented and configured annual charges.
- **Each update discards a fractional fee** — `modules/cdp/cdp.vy._accrue` · seen in 3/3 runs · NEW · [agents: 1,5,6] — Code smells: The index advances while the aggregate minted fee rounds down. — Unverified: A material amplification beyond less than one base unit per update; calculate an economic upper bound before promotion.
- **A small surplus can fall below one purchase unit** — `modules/cdp/cdp.vy._buy_surplus` · seen in 1/3 runs · NEW · [agents: 1,6] — Code smells: The smallest collateral payment can quote more mUSD than the entire remaining surplus, so `bought <= balanceOf[self]` fails. — Unverified: A supported collateral price and material surplus value; calculate the residue bound before treating the minimum-unit effect as a loss.
- **A price update can reduce the purchase output** — `modules/cdp/cdp.vy._buy_surplus` · seen in 3/3 runs · NEW · [agents: 1,3,4,5,6,8,11,12] — Code smells: The shared function has no caller-supplied minimum output. — Unverified: An unprivileged extraction mechanism beyond ordinary quote movement; examine ordering around the configured feed.
- **An old price can overvalue surplus payments** — `modules/cdp/cdp.vy._buy_surplus` · seen in 3/3 runs · NEW · [agents: 6,9] — Code smells: A fixed 0.5% spread may be smaller than an accepted oracle price error. — Unverified: A supported feed, price displacement, available surplus, and profitable unprivileged trade after costs; the fee is present despite the historical label.
- **An old price can overpay reserve collateral** — `modules/cdp/cdp.vy._cover_bad_debt` · seen in 3/3 runs · NEW · [agents: 6,9] — Code smells: The reserve pays collateral at the accepted oracle price less a fixed fee. — Unverified: A reachable reserve and bad-debt state, an accepted price error beyond the fee, and viable extraction after costs.
- **A large liquidation needs the full repayment** — `modules/cdp/cdp.vy._liquidate` · seen in 3/3 runs · NEW · [agents: 1,2,3,4,5,6,7,8,9,11,12] — Code smells: The below-110% branch requires one caller to supply the full repayment. — Unverified: Whether a realistic position exceeds available financing and causes material loss; test financing routes and stressed liquidity.
- **Coarse collateral can round the payout to zero** — `modules/cdp/cdp.vy._liquidate` · seen in 3/3 runs · NEW · [agents: 1,2,3,5,6] — Code smells: The required repayment can buy less than one collateral base unit. — Unverified: A realistic accepted asset and material liquidation size; the supplied example needs a $990-billion token with six decimals.
- **A small liquidation can remove zero debt shares** — `modules/cdp/cdp.vy._liquidate` · seen in 2/3 runs · NEW · [agents: 1,2,3,4,5,8,10] — Code smells: `_repay` rounds removed shares down, but `_liquidate` can still pay collateral. — Unverified: A reachable index, price, and transaction cost that make this loss material; prove amplification beyond the current share-unit bound.
- **An oracle floor can exceed the market price** — `modules/cdp/cdp.vy._price` · seen in 3/3 runs · NEW · [agents: 3,6,9] — Code smells: The function accepts any positive answer within its timeout. — Unverified: Whether the actual selected feed has a reachable floor above market value; inspect the deployed aggregator configuration.
- **A retired feed can block price-dependent calls** — `modules/cdp/cdp.vy._price` · seen in 3/3 runs · NEW · [agents: 3,6,7,9] — Code smells: The oracle is immutable and old answers revert. — Unverified: A selected feed retirement and unavailable recovery path; assess repayment and debt-free withdrawal before claiming a permanent lock.
- **An old price can overpay a redemption** — `modules/cdp/cdp.vy._redeem` · seen in 3/3 runs · NEW · [agents: 3,6,9] — Code smells: The payout increases when the accepted oracle price is below the market price. — Unverified: A supported feed lag larger than that fee and a profitable, materially harmful trade; verify the market and feed together.
- **A small redemption can remove zero debt shares** — `modules/cdp/cdp.vy._redeem` · seen in 1/3 runs · NEW · [agents: 1,10] — Code smells: At index 3e18, four shares owe 12 base units; a two-unit redemption pays one collateral unit and removes zero shares. — Unverified: A reachable index and economically material amplification beyond base-unit dust; include token costs, transaction costs, and the post-redemption ratio check on later calls.
- **An oracle outage blocks withdrawals that retain debt** — `modules/cdp/cdp.vy._withdraw` · seen in 3/3 runs · NEW · [agents: 2,3,5,6,7] — Code smells: The collateral-ratio check requires an oracle answer when debt remains. — Unverified: A material outage and users unable to repay; burn itself reads no price and debt-free withdrawals skip the oracle.
- **Interest can leave debt after a quoted repayment** — `modules/cdp/cdp.vy.burn` · seen in 3/3 runs · NEW · [agents: 1,5,6,7,8,9] — Code smells: The caller submits an exact amount before the contract accrues interest. — Unverified: Material collateral lock and the absence of an execution-time repayment route; evaluate actual borrower and client paths.
- **Small positions can offer small liquidation rewards** — `modules/cdp/cdp.vy.mint` · seen in 2/3 runs · NEW · [agents: 1,3,6,7] — Code smells: The function sets no minimum debt. — Unverified: A realistic low-cost creation path and material aggregate harm; quantify liquidation rewards and transaction costs.

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
