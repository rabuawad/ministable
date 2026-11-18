import boa
import pytest

from tests.mocks.deployers import MOCK_AGGREGATOR
from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    ORACLE_TIMEOUT,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    SEQUENCER_GRACE_PERIOD,
)
from tests.utils.helpers import deploy_cdp_erc20, fund, to_feed_price

SEQUENCER_UP = 0
SEQUENCER_DOWN = 1


# ================= Price feed =================


def test_price_at_timeout_is_fresh(cdp, borrower_position):
    boa.env.time_travel(seconds=ORACLE_TIMEOUT)

    cdp.mint(1, sender=borrower_position)


def test_stale_price_reverts(cdp, borrower_position):
    boa.env.time_travel(seconds=ORACLE_TIMEOUT + 1)

    with boa.reverts(dev="[cdp] stale price"):
        cdp.mint(1, sender=borrower_position)


def test_refreshed_price_unblocks(cdp, oracle, borrower_position):
    boa.env.time_travel(seconds=ORACLE_TIMEOUT + 1)
    oracle.set_answer(to_feed_price(2000))

    cdp.mint(1, sender=borrower_position)


@pytest.mark.parametrize("answer", [0, -1])
def test_non_positive_price_reverts(cdp, oracle, borrower_position, answer):
    oracle.set_answer(answer)

    with boa.reverts(dev="[cdp] invalid price"):
        cdp.mint(1, sender=borrower_position)
    with boa.reverts(dev="[cdp] invalid price"):
        cdp.collat_ratio(borrower_position)


def test_custom_oracle_timeout(token, oracle, borrower):
    cdp = deploy_cdp_erc20(token.address, oracle.address, timeout=2 * ORACLE_TIMEOUT)
    fund(token, cdp, borrower)
    cdp.deposit(ETH, sender=borrower)
    boa.env.time_travel(seconds=2 * ORACLE_TIMEOUT)

    cdp.mint(1, sender=borrower)

    boa.env.time_travel(seconds=1)
    with boa.reverts(dev="[cdp] stale price"):
        cdp.mint(1, sender=borrower)


def test_burn_ignores_price(cdp, oracle, borrower_position):
    """Repaying never reads the price, so it works with a broken feed."""
    oracle.set_answer(0)

    cdp.burn(POSITION_DEBT, sender=borrower_position)

    assert cdp.debt(borrower_position) == 0


# ================= L2 sequencer =================


@pytest.fixture
def sequencer():
    feed = MOCK_AGGREGATOR.deploy(SEQUENCER_UP, 0)
    # Up since well before the grace period.
    boa.env.time_travel(seconds=SEQUENCER_GRACE_PERIOD + 1)
    return feed


@pytest.fixture
def l2_cdp(token, oracle, sequencer, borrower):
    oracle.set_answer(ETH_USD_PRICE)
    cdp = deploy_cdp_erc20(token.address, oracle.address, sequencer=sequencer.address)
    fund(token, cdp, borrower)
    cdp.deposit(POSITION_COLLATERAL, sender=borrower)
    cdp.mint(POSITION_DEBT, sender=borrower)
    return cdp


def test_sequencer_feed_is_set(l2_cdp, sequencer):
    assert l2_cdp.SEQUENCER_UPTIME_FEED() == sequencer.address


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
    """Depositing, repaying and withdrawing a debt-free position never read the price."""
    sequencer.set_answer(SEQUENCER_DOWN)

    l2_cdp.burn(POSITION_DEBT, sender=borrower)
    l2_cdp.withdraw(POSITION_COLLATERAL, sender=borrower)
    l2_cdp.deposit(ETH, sender=borrower)

    assert l2_cdp.debt(borrower) == 0
    assert l2_cdp.collateral(borrower) == ETH
