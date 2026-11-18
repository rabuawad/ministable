from tests.utils.constants import ETH, MAX_UINT256
from tests.utils.helpers import to_feed_price


def test_no_debt_is_max(cdp, borrower):
    assert cdp.collat_ratio(borrower) == MAX_UINT256


def test_collateral_without_debt_is_max(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)

    assert cdp.collat_ratio(borrower) == MAX_UINT256


def test_ratio_value(cdp, borrower_position):
    """$2000 of ETH backing $1000 of debt."""
    assert cdp.collat_ratio(borrower_position) == 2 * 10**18


def test_ratio_scales_with_price(cdp, oracle, borrower_position):
    oracle.set_answer(to_feed_price(3000))

    assert cdp.collat_ratio(borrower_position) == 3 * 10**18


def test_ratio_scales_with_collateral(cdp, borrower_position):
    cdp.deposit(value=ETH, sender=borrower_position)

    assert cdp.collat_ratio(borrower_position) == 4 * 10**18
