"""`PRICE_SCALE` folds the token's and the feed's decimals into one factor,
so every amount below is checked across real-world decimal pairs."""

import boa
import pytest

from tests.mocks.deployers import MOCK_AGGREGATOR, MOCK_TOKEN
from tests.utils.constants import (
    ETH,
    MAX_UINT256,
    MIN_COLLAT_RATIO,
    PRECISION,
)
from tests.utils.helpers import (
    deploy_cdp_erc20,
    fund,
    liquidation,
    max_mintable,
    price_scaled,
    redemption_fee,
    to_feed_price,
)

# (collateral decimals, feed decimals, whole-dollar price)
MARKETS = {
    "usdc": (6, 8, 1),
    "wbtc": (8, 8, 60_000),
    "weth-18-feed": (18, 18, 2_000),
    "weth-0-feed": (18, 0, 2_000),
    "usdc-18-feed": (6, 18, 1),
}

# Each position locks 3 whole tokens and mints one token's worth of mUSD: 300%.
TOKENS = 3


@pytest.fixture(params=MARKETS.values(), ids=MARKETS.keys())
def market(request, borrower, liquidator):
    token_decimals, feed_decimals, usd = request.param
    token = MOCK_TOKEN.deploy(token_decimals)
    feed = MOCK_AGGREGATOR.deploy(to_feed_price(usd, feed_decimals), feed_decimals)
    cdp = deploy_cdp_erc20(token.address, feed.address)
    unit = 10**token_decimals
    for account in (borrower, liquidator):
        fund(token, cdp, account, 1_000 * unit)
    # The liquidator holds mUSD from a large, safe position.
    cdp.deposit(100 * unit, sender=liquidator)
    cdp.mint(10 * usd * ETH, sender=liquidator)
    return {
        "cdp": cdp,
        "token": token,
        "feed": feed,
        "unit": unit,
        "usd": usd,
        "token_decimals": token_decimals,
        "feed_decimals": feed_decimals,
    }


@pytest.fixture
def position(market, borrower):
    cdp, unit, usd = market["cdp"], market["unit"], market["usd"]
    cdp.deposit(TOKENS * unit, sender=borrower)
    cdp.mint(usd * ETH, sender=borrower)
    return borrower


def test_collat_ratio_is_decimal_independent(market, position):
    assert market["cdp"].collat_ratio(position) == TOKENS * PRECISION


def test_max_mint(market, borrower):
    cdp, unit = market["cdp"], market["unit"]
    feed_price = market["feed"].answer()
    collateral = TOKENS * unit
    limit = max_mintable(
        collateral, feed_price, market["feed_decimals"], market["token_decimals"]
    )
    # Two tokens' worth: 3 tokens at 150%.
    assert limit == 2 * market["usd"] * ETH
    cdp.deposit(collateral, sender=borrower)

    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.mint(limit + 1, sender=borrower)
    cdp.mint(limit, sender=borrower)

    assert cdp.collat_ratio(borrower) == MIN_COLLAT_RATIO


def test_partial_liquidation(market, position, liquidator):
    """At 45% of the price the position is at 135%: partly liquidated back to 150%."""
    cdp, token, feed = market["cdp"], market["token"], market["feed"]
    feed_price = feed.answer() * 45 // 100
    feed.set_answer(feed_price)
    liquidator_tokens = token.balanceOf(liquidator)
    repaid, seized, written_off = liquidation(
        TOKENS * market["unit"],
        market["usd"] * ETH,
        feed_price,
        MAX_UINT256,
        market["feed_decimals"],
        collateral_decimals=market["token_decimals"],
    )
    assert written_off == 0

    assert cdp.liquidate(position, MAX_UINT256, sender=liquidator) == repaid

    assert cdp.collateral(position) == TOKENS * market["unit"] - seized
    assert cdp.collat_ratio(position) >= MIN_COLLAT_RATIO
    assert token.balanceOf(liquidator) == liquidator_tokens + seized


def test_insolvent_liquidation(market, position, liquidator):
    """At 30% of the price the position is at 90%: closed, the gap written off."""
    cdp, feed = market["cdp"], market["feed"]
    feed_price = feed.answer() * 30 // 100
    feed.set_answer(feed_price)
    repaid, seized, written_off = liquidation(
        TOKENS * market["unit"],
        market["usd"] * ETH,
        feed_price,
        MAX_UINT256,
        market["feed_decimals"],
        collateral_decimals=market["token_decimals"],
    )
    assert seized == TOKENS * market["unit"]

    assert cdp.liquidate(position, MAX_UINT256, sender=liquidator) == repaid

    assert cdp.collateral(position) == 0
    assert cdp.bad_debt() == written_off > 0


def test_redeem(market, position, liquidator):
    """Redeeming one token's worth of mUSD pays one token, less the fee."""
    cdp, token = market["cdp"], market["token"]
    amount = market["usd"] * ETH
    price = price_scaled(market["feed"].answer(), market["feed_decimals"], market["token_decimals"])
    # The position is at 300%: a 2% fee.
    expected = amount * (PRECISION - redemption_fee(TOKENS * PRECISION)) // price

    paid = cdp.redeem(position, amount, 1, sender=liquidator)

    assert paid == expected
    assert market["unit"] * 98 // 100 - 1 <= paid <= market["unit"]


def test_round_trip(market, position):
    """Close the position: every base unit of collateral comes back."""
    cdp, token, unit = market["cdp"], market["token"], market["unit"]
    tokens = token.balanceOf(position)

    cdp.burn(market["usd"] * ETH, sender=position)
    cdp.withdraw(TOKENS * unit, sender=position)

    assert token.balanceOf(position) == tokens + TOKENS * unit
    assert cdp.collateral(position) == 0
