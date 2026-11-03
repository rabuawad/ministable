# ministable (mUSD)

A minimal stablecoin in Vyper, backed by the chain's native coin and inspired
by DAI / Sky USD and
[MicroStable](https://github.com/shafu0x/MicroStable-World/tree/main/vyper).
Unlike MicroStable, the CDP engine lives inside the token contract: one
contract holds the collateral, tracks positions and mints/burns mUSD.

| File | Contents |
| --- | --- |
| `src/ministable.vy` | The deployed token: wires the modules below together and treats plain transfers as deposits |
| `modules/tokens/erc20.vy` | ERC-20 + EIP-2612 permit |
| `modules/cdp/cdp.vy` | The collateral-agnostic CDP engine: positions, debt, interest, liquidations, redemptions, bad debt, surplus and the oracle. It never moves collateral; its internal functions return what to pay out, and `VARIANT` records which kind of collateral backs it |
| `modules/cdp/cdp_native.vy` | Wraps `cdp` with the native coin as collateral: receives it via `deposit` and sends it with `raw_call` |
| `modules/cdp/cdp_erc20.vy` | Wraps `cdp` with an ERC-20 token (USDC, USDT, WETH, …) as collateral: pulls and sends the token, crediting what actually arrives. Not wired into a deployed contract yet |

## Mechanism

- **Collateral:** the chain's native coin: ETH on Ethereum, Arbitrum and Base,
  MON on Monad, S on Sonic. Lock it by calling `deposit()` or by sending it directly
  to the contract — both route through the internal `_deposit`.
- **Minimum collateral ratio:** 150%. Minting and withdrawing must leave the
  position at or above it.
- **Price:** a Chainlink AggregatorV3 feed for the native coin in USD (any
  decimals up to 18). Non-positive or stale answers revert. The staleness
  limit, `ORACLE_TIMEOUT`, is set per network at deployment (the feed's
  heartbeat plus a buffer) and is immutable afterwards.
- **L2 sequencer:** on rollups such as Arbitrum and Base, the contract reads Chainlink's
  sequencer uptime feed and refuses to price positions while the sequencer is
  down and for an hour after it returns. L1s (Ethereum, Monad, Sonic) have no
  sequencer and deploy without the feed, which skips the check. `deposit`,
  `burn` and debt-free `withdraw` never read the price, so users can always
  repay and exit.
- **Stability fee:** debt grows at a fixed per-second rate (`STABILITY_FEE`,
  set at deployment, capped at 10% a year). The deploy script charges 2% a year,
  and 3.75% on Monad, Monad testnet, Base and Base Sepolia. Interest is minted to the contract
  as the **surplus**. Anyone can buy surplus
  mUSD with the native coin at the oracle price, less a 0.5% fee, through
  `buy_surplus()`, which is how the extra mUSD that borrowers owe as interest reaches the market. The
  coin paid goes to the `reserve`.
- **Liquidation:** any position below 150% can be liquidated. The liquidator
  repays mUSD and receives 110% of it in collateral (a 10% bonus). They repay
  only what brings the position back to 150%, so the borrower keeps the rest of
  their collateral.
- **Bad debt:** if a position's collateral is worth less than 110% of its debt
  but still covers it, the liquidator repays the whole debt and takes all of the
  collateral, so the bonus shrinks to zero at 100% and nothing is written off.
  Below 100%, the liquidator repays what the collateral covers at 110% and takes
  all of it; the rest of the debt is written off as `bad_debt`. The surplus absorbs bad
  debt automatically. What it can't absorb, anyone can retire with
  `cover_bad_debt(amount)`, which burns their mUSD for native coin from the
  reserve at the oracle price, less a 0.5% fee. Both swap fees (`SWAP_FEE`)
  stop callers from trading against the protocol at a lagging oracle price.
- **Redemptions:** anyone can swap mUSD for $1 of collateral per mUSD from any
  healthy position with `redeem(user, amount, min_paid)`, less a fee that stays
  with the borrower. This puts a floor under the peg. The redeemer picks the
  position, since sorting positions by risk on-chain (as Liquity does) costs too
  much for a contract this small. Instead the fee rises with the position's
  ratio: 0.5% at 150%, plus 1% per 100% above it, capped at 5% from 600%. A
  redeemer pays least for the riskiest positions, so those are redeemed first,
  and safer borrowers keep more when they are redeemed. `min_paid` (default 0)
  reverts the call if the borrower adds collateral first and the fee rises.
- **Token:** ERC-20 + EIP-2612 permit, 18 decimals.

| Function | Description |
| --- | --- |
| `deposit()` / plain transfer | Lock `msg.value` of the native coin as collateral |
| `mint(amount)` | Mint mUSD against your collateral (ratio ≥ 150%) |
| `burn(amount)` | Burn mUSD to repay your debt |
| `withdraw(amount)` | Withdraw collateral (ratio must stay ≥ 150%) |
| `liquidate(user, max_repay)` | Repay up to `max_repay` of `user`'s debt for 110% of it in collateral (ratio < 150%) |
| `redeem(user, amount, min_paid)` | Burn `amount` mUSD of `user`'s debt for $1 of their collateral each, less a 0.5–5% fee that rises with the ratio (ratio ≥ 150%) |
| `cover_bad_debt(amount)` | Burn `amount` mUSD of bad debt for its value in reserve coin, less 0.5% |
| `buy_surplus()` | Buy surplus mUSD with the sent native coin at the oracle price, less 0.5% |
| `collat_ratio(user)` | 1e18-scaled collateral ratio (`1.5e18` = 150%) |
| `collateral(user)` / `debt(user)` | Position state (`debt` includes interest) |
| `surplus()` / `reserve()` / `bad_debt()` | Protocol-held mUSD (unsold interest), native coin (from surplus sales) and unbacked mUSD |

## Quickstart

```bash
mox compile        # compile
mox test           # run the test suite
mox run deploy     # deploy with a mock $2000 oracle on pyevm
```

The price feed is the `native_usd_price_feed` named contract in
`moccasin.toml`. It must quote the network's native coin in USD: pinning an
ETH/USD feed on Monad or Sonic would value MON or S as if it were ETH. Local
networks (pyevm, anvil) deploy `tests/mocks/mock_aggregator.vy`; live networks
use the Chainlink feed address pinned there and refuse to deploy a mock.
Monad testnet is the exception: Chainlink has no MON/USD feed there, so the
script deploys that same mock at $2000. Only the deployer can change the
answer.

```bash
mox run deploy --network sepolia --fork             # dry run against a Sepolia fork
mox run deploy --network sepolia --account <name>   # live deploy + Etherscan verification
mox run deploy --network base --fork                # dry run against a Base fork
mox run deploy --network base --account <name>      # live deploy + Basescan verification
mox run deploy --network base_sepolia --fork        # dry run against a Base Sepolia fork
mox run deploy --network base_sepolia --account <name>  # live deploy + Basescan verification
mox run deploy --network monad_testnet --fork       # dry run; local mock feed, nothing sent
mox run deploy --network monad_testnet --account <name>  # live deploy + Monadscan verification
mox run verify --network monad_testnet             # re-verify the latest recorded deployment
```

Each live network sets `oracle_timeout` under `[networks.<name>.extra_data]`,
and L2s pin a `sequencer_uptime_feed` contract (the script refuses to deploy to
Arbitrum or Base without one). Chainlink publishes no sequencer feed for Base
Sepolia, so that testnet deploys without the check.

| Network | Chain ID | Collateral | Chainlink feed | Feed heartbeat | `oracle_timeout` | Sequencer feed |
| --- | --- | --- | --- | --- | --- | --- |
| Ethereum mainnet | 1 | ETH | ETH/USD `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419` | 3600s | 4500s | — |
| Sepolia | 11155111 | ETH | ETH/USD `0x694AA1769357215DE4FAC081bf1f309aDC325306` | 3600s | 4500s | — |
| Arbitrum One | 42161 | ETH | ETH/USD `0x639Fe6ab55C921f74e7fac1ee960C0B6293ba612` | 1755s | 2400s | `0xFdB631F5EE196F0ed6FAa767959853A9F217697D` |
| Base | 8453 | ETH | ETH/USD `0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70` | 1200s | 1800s | `0xBCF85224fc0756B9Fa45aA7892530B47e10b6433` |
| Base Sepolia | 84532 | ETH | ETH/USD `0x4aDC67696bA383F43DD60A9e78F2C97Fbbfc7cb1` | 1200s | 1800s | — (none published) |
| Monad | 143 | MON | MON/USD `0xBcD78f76005B7515837af6b50c7C52BCf73822fb` | 3600s | 4500s | — |
| Monad testnet | 10143 | MON | owner-gated mock at $2000, deployed by the script | — | 365 days | — |
| Sonic | 146 | S | S/USD `0xc76dFb89fF298145b417d221B2c747d84952e01d` | 86400s | 90000s | — |

Sonic's feed updates only every 24 hours or on a 0.5% price move, so
liquidations there react to prices more slowly than on the other networks.

Before deploying, the script checks that the feed is a contract, reports at most
18 decimals and has a fresh, positive answer, and that the sequencer (if any) is
up and past its grace period. After deploying, it reads the contract back to
confirm its parameters. Verification needs `ETHERSCAN_API_KEY` in `.env`
(Etherscan's v2 API covers every network above, including Monad testnet as
chain id `10143`; verified source shows on
[testnet.monadscan.com](https://testnet.monadscan.com)). Mainnet, Arbitrum,
Monad, Monad testnet, Sonic and Base also need `MAINNET_RPC_URL`,
`ARBITRUM_RPC_URL`, `MONAD_RPC_URL`, `MONAD_TESTNET_RPC_URL`,
`SONIC_RPC_URL` and `BASE_RPC_URL`.

Monad testnet has no Chainlink MON/USD feed, so the live deploy broadcasts
two contracts: the mock, then ministable. Both are submitted for verification.
The mock's initial answer is $2000 and stays valid for a year; `set_answer`
after that is limited to the deploying account.

## Tests

The tests exercise the modules, not `src/ministable.vy`: each module is
deployed inside a small harness contract in `tests/mocks/`.

| Directory | Contents |
| --- | --- |
| `tests/unitary/cdp_native/` | One file per behavior: deposit, mint, burn, withdraw, liquidate, redeem, stability fee, oracle, collateral ratio |
| `tests/unitary/cdp_erc20/` | The same behaviors with ERC-20 collateral, plus fee-on-transfer, no-return and `False`-returning tokens, re-entrant token callbacks, and collateral decimals from 6 to 18 and feed decimals from 0 to 18 |
| `tests/unitary/erc20/` | The token on its own: transfers, allowances, mint/burn, metadata, permit |
| `tests/unitary/factory/` | The factory deploying `ministable` from its blueprint |
| `tests/integration/` | Multi-step `cdp_native` position lifecycles (open/close, rescue, liquidation with bought mUSD) |
| `tests/fuzz/` | Hypothesis on `cdp_native`: exact mint/withdraw bounds, and a stateful model of interest, liquidations, bad debt, surplus and redemptions checking solvency invariants |
| `tests/mocks/` | Module harnesses (`cdp_native`, `cdp_erc20`, `erc20`), a mock Chainlink feed, mock collateral tokens, and a contract position holder (rejecting the native coin, reentrancy) |

```bash
mox test tests/unitary   # fast unit tests only
mox test tests/fuzz      # property + stateful fuzzing (~45s)
FUZZ_EXAMPLES=1000 mox test tests/fuzz   # deeper stateful run (~10 min)
```

The stateful model checks after every step that:

- every position, balance, the rate index, surplus, reserve and bad debt match
  an independent reference model;
- total debt plus bad debt equals mUSD supply (plus interest not yet minted),
  with rounding only ever in the protocol's favour;
- the native coin the contract holds equals total collateral plus the reserve,
  and none is created or destroyed;
- a liquidation not capped by `max_repay` leaves the position at 150% or more,
  and a redemption never lowers the redeemed position's ratio.

## Status

ministable has not been audited. Mainnet, Arbitrum, Base, Monad and Sonic are
configured (with `prompt_live = true`), but don't deploy there before an outside
review of the frozen code, such as a competitive audit.
