"""Property tests for `cdp_erc20` across collateral decimals, with interest.

The stateful solvency fuzzer runs on 18-decimal native collateral. Coarser
tokens (USDC's 6, WBTC's 8) floor every collateral amount harder, which is
where liquidation and redemption rounding is tightest, so these draw a
random market, position, elapsed time and price crash, and check each
operation against the reference maths in `tests/utils/helpers.py`."""

import boa
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from tests.mocks.deployers import MOCK_AGGREGATOR, MOCK_TOKEN
from tests.utils.constants import (
    MAX_STABILITY_FEE,
    MAX_UINT256,
    MIN_COLLAT_RATIO,
    PRECISION,
    YEAR,
)
from tests.utils.helpers import (
    deploy_cdp_erc20,
    fund,
    liquidation,
    max_mintable,
    price_scaled,
    redemption_fee,
)

FEED_DECIMALS = 8

decimals_st = st.sampled_from([6, 8, 18])
# $0.01 to $100k per whole token.
feed_price_st = st.integers(min_value=10**6, max_value=10**5 * 10**FEED_DECIMALS)
# Position size in whole-token hundredths: 0.01 to 1M tokens.
size_st = st.integers(min_value=1, max_value=10**8)
elapsed_st = st.integers(min_value=0, max_value=2 * YEAR)
drop_bps_st = st.integers(min_value=0, max_value=9_500)

SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _market(decimals, feed_price, borrower, liquidator, size):
    """A max-fee market where `borrower` mints to the limit against `size`
    hundredths of a token, and `liquidator` holds a far safer position with
    twice that mUSD."""
    unit = 10**decimals
    collateral = size * unit // 100
    token = MOCK_TOKEN.deploy(decimals)
    feed = MOCK_AGGREGATOR.deploy(feed_price, FEED_DECIMALS)
    cdp = deploy_cdp_erc20(token.address, feed.address, fee=MAX_STABILITY_FEE)
    fund(token, cdp, borrower, collateral)
    fund(token, cdp, liquidator, 100 * collateral)

    limit = max_mintable(collateral, feed_price, collateral_decimals=decimals)
    assume(limit > 0)
    cdp.deposit(collateral, sender=borrower)
    cdp.mint(limit, sender=borrower)

    cdp.deposit(100 * collateral, sender=liquidator)
    cdp.mint(2 * limit, sender=liquidator)
    return cdp, token, feed, collateral


def _wait_and_move(feed, elapsed, feed_price, drop_bps) -> int:
    boa.env.time_travel(seconds=elapsed)
    new_price = max(feed_price * (10_000 - drop_bps) // 10_000, 1)
    feed.set_answer(new_price)
    return new_price


def _assert_solvent(cdp, token, accounts):
    """The contract holds exactly the collateral it owes, and every mUSD is
    owed back by a borrower or recorded as bad debt (rounding favours the
    protocol by at most a few wei per position)."""
    owed = sum(cdp.collateral(a) for a in accounts) + cdp.reserve()
    assert token.balanceOf(cdp.address) == owed

    cdp.mint(0, sender=accounts[0])  # accrue, so the surplus is minted
    supply = cdp.totalSupply()
    total_debt = sum(cdp.debt(a) for a in accounts) + cdp.bad_debt()
    assert supply <= total_debt <= supply + 4 * len(accounts)


@SETTINGS
@given(
    decimals=decimals_st,
    feed_price=feed_price_st,
    size=size_st,
    elapsed=elapsed_st,
    drop_bps=drop_bps_st,
)
def test_liquidation(borrower, liquidator, decimals, feed_price, size, elapsed, drop_bps):
    """A liquidation repays and seizes exactly what the reference maths says,
    leaves the position at or above 150% unless it closes it, and never
    seizes more than the position holds."""
    with boa.env.anchor():
        cdp, token, feed, collateral = _market(
            decimals, feed_price, borrower, liquidator, size
        )
        price = _wait_and_move(feed, elapsed, feed_price, drop_bps)

        if cdp.collat_ratio(borrower) >= MIN_COLLAT_RATIO:
            with boa.reverts(dev="[cdp] position healthy"):
                cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
            return

        debt = cdp.debt(borrower)
        liquidator_tokens = token.balanceOf(liquidator)

        repaid = cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
        expected = liquidation(
            collateral,
            debt,
            price,
            MAX_UINT256,
            rate_index=cdp.rate_index(),
            collateral_decimals=decimals,
        )
        seized = token.balanceOf(liquidator) - liquidator_tokens

        assert (repaid, seized) == expected[:2]
        assert seized <= collateral
        if expected[2] == 0 and cdp.debt(borrower) > 0:
            assert cdp.collat_ratio(borrower) >= MIN_COLLAT_RATIO
        else:
            assert cdp.debt(borrower) == 0
            assert cdp.collateral(borrower) == 0
        _assert_solvent(cdp, token, [borrower, liquidator])


@SETTINGS
@given(
    decimals=decimals_st,
    feed_price=feed_price_st,
    size=size_st,
    elapsed=elapsed_st,
    rise_bps=st.integers(min_value=0, max_value=50_000),
    share_bps=st.integers(min_value=1, max_value=10_000),
)
def test_redemption(
    borrower, liquidator, decimals, feed_price, size, elapsed, rise_bps, share_bps
):
    """A redemption pays $1 of collateral per mUSD less the ratio-based fee,
    never lowers the redeemed position's ratio, and keeps the books balanced."""
    with boa.env.anchor():
        cdp, token, feed, _ = _market(decimals, feed_price, borrower, liquidator, size)
        # A rising price spreads positions across the fee curve.
        boa.env.time_travel(seconds=elapsed)
        price = feed_price * (10_000 + rise_bps) // 10_000
        feed.set_answer(price)

        ratio = cdp.collat_ratio(borrower)
        debt = cdp.debt(borrower)
        amount = max(debt * share_bps // 10_000, 1)

        if ratio < MIN_COLLAT_RATIO:
            with boa.reverts(dev="[cdp] position unhealthy"):
                cdp.redeem(borrower, amount, sender=liquidator)
            return

        expected = amount * (PRECISION - redemption_fee(ratio)) // price_scaled(
            price, FEED_DECIMALS, decimals
        )
        # Asking for one unit more than the fee curve pays trips the slippage guard.
        with boa.reverts(dev="[cdp] slippage"):
            cdp.redeem(borrower, amount, expected + 1, sender=liquidator)

        liquidator_tokens = token.balanceOf(liquidator)
        paid = cdp.redeem(borrower, amount, expected, sender=liquidator)

        assert paid == expected
        assert token.balanceOf(liquidator) == liquidator_tokens + paid
        assert cdp.collat_ratio(borrower) >= ratio
        _assert_solvent(cdp, token, [borrower, liquidator])


@SETTINGS
@given(decimals=decimals_st, feed_price=feed_price_st, size=size_st, elapsed=elapsed_st)
def test_round_trip_never_profits(borrower, liquidator, decimals, feed_price, size, elapsed):
    """Repaying every mUSD owed and withdrawing everything returns at most the
    collateral deposited: interest and rounding cannot be gamed into a profit."""
    with boa.env.anchor():
        cdp, token, feed, collateral = _market(
            decimals, feed_price, borrower, liquidator, size
        )
        boa.env.time_travel(seconds=elapsed)
        feed.set_answer(feed_price)

        debt = cdp.debt(borrower)
        # Interest is owed on top of what was minted; borrow it from the liquidator.
        cdp.transfer(borrower, debt - cdp.balanceOf(borrower), sender=liquidator)
        cdp.burn(debt, sender=borrower)
        cdp.withdraw(collateral, sender=borrower)

        assert cdp.debt(borrower) == 0
        assert cdp.debt_shares(borrower) == 0
        assert cdp.collateral(borrower) == 0
        assert token.balanceOf(borrower) == collateral
        assert cdp.balanceOf(borrower) == 0
        _assert_solvent(cdp, token, [borrower, liquidator])
