<!--RUN pass=1 agents=12/12-->

Completeness: 15 unique (file, function) in raw, 12 covered in final, 3 rejected with reasons.

All twelve specialties completed. The review uses the frozen four-module source. The local environment has no importable Vyper compiler, so validation consists of source traces and integer calculations, not compiled execution.

Gate decisions:
- `_push` sender surcharge: execution ALLOWS; realistic token behavior ALLOWS; an ordinary withdrawal ALLOWS; another depositor's material deficit ALLOWS. A deployment with that fee is a specific achievable state (-10). No compiler advisory is assumed.
- `redeem` net minimum: execution ALLOWS; ordinary recipient-fee behavior ALLOWS; an ordinary redemption ALLOWS; loss beyond the explicit minimum ALLOWS. A deployment with that fee is a specific achievable state (-10). This is conditional token compatibility, not a claim about a deployed USDC or WETH instance.
- `_push` also contains the recipient-fee mechanism reported by specialties 8, 9 and 12. Its trace and distinct fix remain in the `redeem` block; the sender-debit mechanism remains in `_push`. These are distinct checks, not interchangeable fixes.
- `src/ministable.vy.__init__`: rejected before gates because the host constructor is outside the named module scope. Generic token metadata is not itself a defect in `modules/tokens/erc20.vy`.
- `cdp_erc20.buy_surplus` and `cdp_native.buy_surplus`: rejected as findings at trigger/impact. A lower oracle quote at inclusion proves price movement, not an unprivileged extraction route. The shared-core minimum-output concern survives as a lead at its original location.
- `_accrue` discarded fractions: impact DEMOTED. Each update loses less than one stablecoin base unit. Even one update per second for a year loses less than 3.1536e-11 mUSD; no material amplification was shown.
- `mint` small debt: impact DEMOTED. There is no shared iteration over all positions, and the agents did not show material aggregate impairment after creation costs.
- `burn` exact repayment: impact DEMOTED. A prior quote can leave a remainder, but the evidence does not establish material locked collateral or rule out execution-time repayment through a borrower contract.
- `_liquidate` liquidity and coarse units: reachability/economics UNCERTAIN. A $990-billion token example does not establish a realistic accepted asset; the full-balance example does not rule out financing. The claims remain leads.
- `_price`, oracle-dependent paths, and oracle-lag swaps: deployed feed behavior and material economics UNCERTAIN. Repeated prior-memory labels are not independent proof of the missing deployed fact; convergence does not replace the gates.
- `liquidate` token pause: the administrator intentionally pausing a token has no demonstrated unprivileged amplifier, so that mechanism is rejected under the admin-action rule. The distinct zero-transfer compatibility lead survives at the same function.

Fix verification: both selected suggestions preserve the asserted transfer result and intentional no-return-token support. A sender-debit check reverts the entire withdrawal when the token takes an excess fee; existing accounting and token effects roll back. A post-transfer recipient check reverts the entire redemption when its actual receipt is below the minimum. Neither suggestion grants a new callback entry point; both use static balance reads under the wrapper's nonreentrancy setting. Rejecting sender-surcharge transfers intentionally limits collateral compatibility; a balance check does not make a dishonest token safe. No source file was changed.

<!--F key=modules-cdp-cdp-erc20-vy|-push|fee-on-transfer-outflow conf=90 kind=FINDING agents=1,2,3,4,5,6,7,8,9,11,12-->

[90] **A sender fee consumes other users' collateral**

`modules/cdp/cdp_erc20.vy._push` · Confidence: 90

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

<!--/F-->

<!--F key=modules-cdp-cdp-erc20-vy|redeem|redemption-net-output-slippage conf=90 kind=FINDING agents=3,5,8,9,12-->

[90] **A transfer fee bypasses the redeemer's minimum**

`modules/cdp/cdp_erc20.vy.redeem` · Confidence: 90

**Description**
A redeemer receives less collateral than `min_paid` because the wrapper checks the nominal transfer amount before the token deducts its fee.

**Proof**
The wrapper advertises transfer-fee support (`modules/cdp/cdp_erc20.vy:12-16`) and promises a minimum collateral payout (`:131-139`). It obtains nominal `paid` from `cdp._redeem`, sends that amount through `_push`, then returns the nominal amount. The core checks `paid >= min_paid` before the transfer (`modules/cdp/cdp.vy:403-414`). `_push` asserts a successful token call but measures no recipient balance (`modules/cdp/cdp_erc20.vy:173-174`).

Use six-decimal collateral at $1, a healthy position with 200 tokens and 100 mUSD debt, and a redeemer with 50 mUSD. At a 200% ratio the redemption fee is 1%: 0.5% plus 1% times the 50% excess ratio. The nominal payout is 49,500,000 base units. Set `min_paid = 49,500,000`. The core passes that check and burns 50 mUSD. A token with a 1% recipient fee returns true but delivers only 49,005,000 base units. The transaction succeeds and returns 49,500,000. The actual receipt falls below the explicit minimum by 495,000 base units; the loss scales with redemption size.

The healthy-position and debt bounds permit this example. No caller access check or nonreentrancy guard checks the actual receipt. This is a supported-token compatibility path, not a claim that a currently deployed token charges that fee. Its root payment helper is `_push`; this block retains the separately reported wrapper location and net-output invariant.

**Fix**
The wrapper should check the recipient's balance increase against `min_paid` after the transfer.

Read the recipient's balance before the payout, then enforce the minimum against the increase after it. Preserve the asserted transfer result and no-return-token policy. A failure must revert the whole redemption, including its debt reduction and stablecoin burn. The sender-debit check in the companion `_push` finding does not replace this recipient check. Rejecting all fee-charging collateral is an alternative policy, but would remove the module's advertised compatibility.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-liquidate|all-or-nothing-liquidation kind=LEAD agents=1,2,3,4,5,7,8,10-->

- **A large liquidation needs the full repayment** — `modules/cdp/cdp.vy._liquidate` — Code smells: The below-110% branch requires one caller to supply the full repayment. — Unverified: Whether a realistic position exceeds available financing and causes material loss; test financing routes and stressed liquidity.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-liquidate|coarse-collateral-zero-seize kind=LEAD agents=3,5,10-->

- **Coarse collateral can round the payout to zero** — `modules/cdp/cdp.vy._liquidate` — Code smells: The required repayment can buy less than one collateral base unit. — Unverified: A realistic accepted asset and material liquidation size; the supplied example needs a $990-billion token with six decimals.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-accrue|caller-driven-compounding kind=LEAD agents=1,6,7-->

- **Callers choose the frequency of interest updates** — `modules/cdp/cdp.vy._accrue` — Code smells: The index compounds each elapsed interval and mint(0) triggers accrual. — Unverified: Whether the intended fee convention differs from this index model; compare documented and configured annual charges.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-accrue|discarded-interest-fractions kind=LEAD agents=1-->

- **Each update discards a fractional fee** — `modules/cdp/cdp.vy._accrue` — Code smells: The index advances while the aggregate minted fee rounds down. — Unverified: A material amplification beyond less than one base unit per update; calculate an economic upper bound before promotion.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|mint|no-minimum-debt kind=LEAD agents=1,7-->

- **Small positions can offer small liquidation rewards** — `modules/cdp/cdp.vy.mint` — Code smells: The function sets no minimum debt. — Unverified: A realistic low-cost creation path and material aggregate harm; quantify liquidation rewards and transaction costs.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|burn|no-full-repay-path kind=LEAD agents=1,3,4,5,6,7-->

- **Interest can leave debt after a quoted repayment** — `modules/cdp/cdp.vy.burn` — Code smells: The caller submits an exact amount before the contract accrues interest. — Unverified: Material collateral lock and the absence of an execution-time repayment route; evaluate actual borrower and client paths.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-buy-surplus|zero-fee-oracle-swap kind=LEAD agents=3-->

- **An old price can overvalue surplus payments** — `modules/cdp/cdp.vy._buy_surplus` — Code smells: A fixed 0.5% spread may be smaller than an accepted oracle price error. — Unverified: A supported feed, price displacement, available surplus, and profitable unprivileged trade after costs; the fee is present despite the historical label.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-cover-bad-debt|zero-fee-oracle-swap kind=LEAD agents=3-->

- **An old price can overpay reserve collateral** — `modules/cdp/cdp.vy._cover_bad_debt` — Code smells: The reserve pays collateral at the accepted oracle price less a fixed fee. — Unverified: A reachable reserve and bad-debt state, an accepted price error beyond the fee, and viable extraction after costs.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-redeem|redemption-oracle-lag-extraction kind=LEAD agents=3,5-->

- **An old price can overpay a redemption** — `modules/cdp/cdp.vy._redeem` — Code smells: The payout uses an accepted oracle answer and a ratio-based fee. — Unverified: A supported feed lag larger than that fee and a profitable, materially harmful trade; verify the market and feed together.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-buy-surplus|missing-purchase-slippage kind=LEAD agents=8-->

- **A price update can reduce the purchase output** — `modules/cdp/cdp.vy._buy_surplus` — Code smells: The shared function has no caller-supplied minimum output. — Unverified: An unprivileged extraction mechanism beyond ordinary quote movement; examine ordering around the configured feed.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-price|chainlink-min-answer-clamp kind=LEAD agents=6,9-->

- **An oracle floor can exceed the market price** — `modules/cdp/cdp.vy._price` — Code smells: The function accepts any positive answer within its timeout. — Unverified: Whether the actual selected feed has a reachable floor above market value; inspect the deployed aggregator configuration.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-price|immutable-oracle-no-fallback kind=LEAD agents=6,9-->

- **A retired feed can block price-dependent calls** — `modules/cdp/cdp.vy._price` — Code smells: The oracle is immutable and old answers revert. — Unverified: A selected feed retirement and unavailable recovery path; assess repayment and debt-free withdrawal before claiming a permanent lock.

<!--/F-->

<!--F key=modules-cdp-cdp-vy|-withdraw|oracle-dependent-withdraw-lock kind=LEAD agents=7,8-->

- **An oracle outage blocks withdrawals that retain debt** — `modules/cdp/cdp.vy._withdraw` — Code smells: The collateral-ratio check requires an oracle answer when debt remains. — Unverified: A material outage and users unable to repay; burn itself reads no price and debt-free withdrawals skip the oracle.

<!--/F-->

<!--F key=modules-cdp-cdp-erc20-vy|liquidate|zero-amount-transfer-revert kind=LEAD agents=1,4,9-->

- **A token can reject a zero collateral payout** — `modules/cdp/cdp_erc20.vy.liquidate` — Code smells: The wrapper calls _push even when seized is zero. — Unverified: A supported token that rejects zero transfers and a material liquidation that must take this path; arbitrary small max_repay alone shows no harm.

<!--/F-->
