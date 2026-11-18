from src import mUSD
from tests.mocks.deployers import CDP_ERC20_HARNESS, CDP_NATIVE_HARNESS, ERC20_HARNESS
from tests.utils.constants import (
    ETH,
    LIQUIDATION_PENALTY,
    MAX_UINT256,
    MIN_COLLAT_RATIO,
    ORACLE_DECIMALS,
    ORACLE_TIMEOUT,
    MAX_REDEMPTION_FEE,
    PRECISION,
    REDEMPTION_FEE,
    REDEMPTION_FEE_SLOPE,
    ZERO_ADDRESS,
)


def deploy_stable(oracle, timeout=ORACLE_TIMEOUT, sequencer=ZERO_ADDRESS, fee=0):
    """The production mUSD contract. Module tests use the harnesses below."""
    return mUSD.deploy(
        "ministable", "mUSD", 18, "ministable", "1", oracle, timeout, sequencer, fee
    )


def deploy_erc20(
    name="ministable", symbol="mUSD", decimals=18, name_eip712="ministable", version_eip712="1"
):
    """The `erc20` test harness, with `mint`/`burn` exposed."""
    return ERC20_HARNESS.deploy(name, symbol, decimals, name_eip712, version_eip712)


def deploy_cdp_native(oracle, timeout=ORACLE_TIMEOUT, sequencer=ZERO_ADDRESS, fee=0):
    """The `cdp_native` test harness. Interest-free by default, so debts stay
    equal to the mUSD minted."""
    return CDP_NATIVE_HARNESS.deploy(oracle, timeout, sequencer, fee)


def deploy_cdp_erc20(collateral, oracle, timeout=ORACLE_TIMEOUT, sequencer=ZERO_ADDRESS, fee=0):
    """The `cdp_erc20` test harness. Interest-free by default, so debts stay
    equal to the mUSD minted."""
    return CDP_ERC20_HARNESS.deploy(collateral, oracle, timeout, sequencer, fee)


def fund(token, cdp, account, amount=100 * ETH):
    """Mint `amount` of the mock collateral `token` to `account` and
    approve `cdp` to pull all of it."""
    token.mint(account, amount)
    token.approve(cdp.address, MAX_UINT256, sender=account)


def held_collateral(cdp, accounts) -> int:
    """Collateral `cdp` owes: every listed position plus the reserve."""
    return sum(cdp.collateral(a) for a in accounts) + cdp.reserve()


def to_feed_price(usd: int, decimals: int = ORACLE_DECIMALS) -> int:
    """Whole-dollar ETH/USD price in a Chainlink feed's format."""
    return usd * 10**decimals


def price_scaled(feed_price: int, decimals: int = ORACLE_DECIMALS, collateral_decimals: int = 18) -> int:
    """USD value of 1e18 base units of collateral, 1e18-scaled (mirrors `_price`)."""
    return feed_price * 10 ** (36 - decimals - collateral_decimals)


def max_mintable(
    collateral: int,
    feed_price: int,
    decimals: int = ORACLE_DECIMALS,
    collateral_decimals: int = 18,
) -> int:
    """Largest debt `collateral` base units can back at `feed_price` (mirrors `_collat_ratio`)."""
    value = collateral * price_scaled(feed_price, decimals, collateral_decimals) // PRECISION
    return value * PRECISION // MIN_COLLAT_RATIO


def redemption_fee(ratio: int) -> int:
    """1e18-scaled redemption fee for a position at `ratio` (mirrors `_redemption_fee`)."""
    return min(
        REDEMPTION_FEE + (ratio - MIN_COLLAT_RATIO) * REDEMPTION_FEE_SLOPE // PRECISION,
        MAX_REDEMPTION_FEE,
    )


def filter_logs(contract, event_name: str, computation=None) -> list:
    """Decoded logs of `contract`'s last call (or of `computation`) named `event_name`."""
    logs = (
        contract.get_logs(computation)
        if computation is not None
        else contract.get_logs()
    )
    return [log for log in logs if type(log).__name__ == event_name]


def liquidation(
    collateral: int,
    debt: int,
    feed_price: int,
    max_repay: int,
    decimals: int = ORACLE_DECIMALS,
    rate_index: int = PRECISION,
    collateral_decimals: int = 18,
) -> tuple[int, int, int]:
    """(repaid, seized, written_off) for a liquidation (mirrors `liquidate`).
    `rate_index` is the contract's index once the call has accrued."""
    price = price_scaled(feed_price, decimals, collateral_decimals)
    value = collateral * price // PRECISION * PRECISION
    if value >= LIQUIDATION_PENALTY * debt:
        step = MIN_COLLAT_RATIO - LIQUIDATION_PENALTY
        debt_margin = rate_index // PRECISION + 1
        needed = MIN_COLLAT_RATIO * (debt + debt_margin) - value + PRECISION
        repay = min(-(-needed // step), debt, max_repay)
        return repay, min(repay * LIQUIDATION_PENALTY // price, collateral), 0
    if value >= debt * PRECISION:
        return debt, collateral, 0
    repay = value // LIQUIDATION_PENALTY
    return repay, collateral, debt - repay
