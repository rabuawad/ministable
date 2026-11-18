import boa
import pytest

from tests.mocks.deployers import MOCK_AGGREGATOR
from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    MIN_COLLAT_RATIO,
    ORACLE_TIMEOUT,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    SEQUENCER_GRACE_PERIOD,
)
from tests.utils.helpers import deploy_cdp_native, max_mintable, to_feed_price

SEQUENCER_UP = 0
SEQUENCER_DOWN = 1


def test_mock_reports_8_decimals(oracle):
    assert oracle.decimals() == 8


def test_price_at_timeout_is_fresh(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)
    boa.env.time_travel(seconds=ORACLE_TIMEOUT)

    cdp.mint(1, sender=borrower)

    assert cdp.debt(borrower) == 1


def test_stale_price_reverts(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)
    boa.env.time_travel(seconds=ORACLE_TIMEOUT + 1)

    with boa.reverts(dev="[cdp] stale price"):
        cdp.mint(1, sender=borrower)


def test_refreshed_price_unblocks(cdp, oracle, borrower):
    cdp.deposit(value=ETH, sender=borrower)
    boa.env.time_travel(seconds=ORACLE_TIMEOUT + 1)
    oracle.set_answer(to_feed_price(2000))

    cdp.mint(1, sender=borrower)


def test_zero_price_reverts(cdp, oracle, borrower):
    cdp.deposit(value=ETH, sender=borrower)
    oracle.set_answer(0)

    with boa.reverts(dev="[cdp] invalid price"):
        cdp.mint(1, sender=borrower)


def test_negative_price_reverts(cdp, oracle, borrower):
    cdp.deposit(value=ETH, sender=borrower)
    oracle.set_answer(-1)

    with boa.reverts(dev="[cdp] invalid price"):
        cdp.mint(1, sender=borrower)


def test_collat_ratio_view_reverts_on_bad_price(cdp, oracle, borrower_position):
    oracle.set_answer(0)

    with boa.reverts(dev="[cdp] invalid price"):
        cdp.collat_ratio(borrower_position)


# ================= Deployment parameters =================


def test_zero_oracle_timeout_reverts(oracle):
    with boa.reverts(dev="[cdp] zero oracle timeout"):
        deploy_cdp_native(oracle.address, timeout=0)


def test_custom_oracle_timeout(oracle, borrower):
    cdp = deploy_cdp_native(oracle.address, timeout=2 * ORACLE_TIMEOUT)
    cdp.deposit(value=ETH, sender=borrower)
    boa.env.time_travel(seconds=2 * ORACLE_TIMEOUT)

    cdp.mint(1, sender=borrower)

    boa.env.time_travel(seconds=1)
    with boa.reverts(dev="[cdp] stale price"):
        cdp.mint(1, sender=borrower)


# ================= Feed decimals =================


@pytest.mark.parametrize("decimals", [0, 6, 8, 18])
def test_feed_decimals_price_the_same(borrower, decimals):
    """$2000 reads as $2000 whatever the feed's decimals."""
    feed = MOCK_AGGREGATOR.deploy(to_feed_price(2000, decimals), decimals)
    cdp = deploy_cdp_native(feed.address)
    limit = max_mintable(POSITION_COLLATERAL, to_feed_price(2000, decimals), decimals)
    assert limit == max_mintable(POSITION_COLLATERAL, ETH_USD_PRICE)

    cdp.deposit(value=POSITION_COLLATERAL, sender=borrower)
    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.mint(limit + 1, sender=borrower)
    cdp.mint(limit, sender=borrower)

    assert cdp.collat_ratio(borrower) >= MIN_COLLAT_RATIO


def test_feed_with_more_than_18_decimals_reverts():
    feed = MOCK_AGGREGATOR.deploy(to_feed_price(2000, 19), 19)

    with boa.reverts(dev="[cdp] unsupported oracle decimals"):
        deploy_cdp_native(feed.address)


# ================= L2 sequencer =================


@pytest.fixture
def sequencer():
    feed = MOCK_AGGREGATOR.deploy(SEQUENCER_UP, 0)
    # Up since well before the grace period.
    boa.env.time_travel(seconds=SEQUENCER_GRACE_PERIOD + 1)
    return feed


@pytest.fixture
def l2_cdp(oracle, sequencer, borrower):
    oracle.set_answer(ETH_USD_PRICE)
    cdp = deploy_cdp_native(oracle.address, sequencer=sequencer.address)
    cdp.deposit(value=POSITION_COLLATERAL, sender=borrower)
    cdp.mint(POSITION_DEBT, sender=borrower)
    return cdp


def test_sequencer_feed_is_set(l2_cdp, sequencer):
    assert l2_cdp.SEQUENCER_UPTIME_FEED() == sequencer.address


def test_sequencer_up_allows_price_reads(l2_cdp, borrower):
    l2_cdp.mint(1, sender=borrower)


def test_sequencer_down_reverts(l2_cdp, sequencer, borrower):
    sequencer.set_answer(SEQUENCER_DOWN)

    with boa.reverts(dev="[cdp] sequencer down"):
        l2_cdp.mint(1, sender=borrower)
    with boa.reverts(dev="[cdp] sequencer down"):
        l2_cdp.collat_ratio(borrower)


def test_sequencer_uninitialised_reverts(l2_cdp, sequencer, borrower):
    sequencer.set_started_at(0)

    with boa.reverts(dev="[cdp] sequencer down"):
        l2_cdp.mint(1, sender=borrower)


def test_sequencer_grace_period(l2_cdp, sequencer, oracle, borrower):
    sequencer.set_answer(SEQUENCER_UP)  # just came back up

    with boa.reverts(dev="[cdp] sequencer grace period"):
        l2_cdp.mint(1, sender=borrower)

    boa.env.time_travel(seconds=SEQUENCER_GRACE_PERIOD)
    oracle.set_answer(ETH_USD_PRICE)
    with boa.reverts(dev="[cdp] sequencer grace period"):
        l2_cdp.mint(1, sender=borrower)

    boa.env.time_travel(seconds=1)
    l2_cdp.mint(1, sender=borrower)


def test_exits_work_while_sequencer_down(l2_cdp, sequencer, borrower):
    """Repaying and withdrawing a debt-free position never read the price."""
    sequencer.set_answer(SEQUENCER_DOWN)

    l2_cdp.burn(POSITION_DEBT, sender=borrower)
    l2_cdp.withdraw(POSITION_COLLATERAL, sender=borrower)
    l2_cdp.deposit(value=ETH, sender=borrower)

    assert l2_cdp.debt(borrower) == 0
    assert l2_cdp.collateral(borrower) == ETH
