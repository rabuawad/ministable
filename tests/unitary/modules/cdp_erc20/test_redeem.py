import boa

from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    MIN_COLLAT_RATIO,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    PRECISION,
    REDEMPTION_FEE,
)
from tests.utils.helpers import filter_logs, price_scaled, redemption_fee, to_feed_price

# The default position's ratio at $2000.
POSITION_RATIO = 2 * PRECISION


def _redeemed(amount: int, ratio: int = POSITION_RATIO, feed_price: int = ETH_USD_PRICE) -> int:
    """Collateral paid for `amount` mUSD from a position at `ratio` (mirrors `redeem`)."""
    return amount * (PRECISION - redemption_fee(ratio)) // price_scaled(feed_price)


def test_redeem(cdp, token, borrower_position, funded_liquidator):
    """Money Flow: redeemer mUSD → burned, $1 of the borrower's collateral less 1% → redeemer."""
    borrower, redeemer = borrower_position, funded_liquidator
    redeemer_tokens = token.balanceOf(redeemer)
    supply = cdp.totalSupply()
    amount = 400 * ETH
    paid = _redeemed(amount)

    assert cdp.redeem(borrower, amount, 1, sender=redeemer) == paid

    assert paid == 198 * ETH // 1000  # $400 at $2000, less 1% at 200%
    assert cdp.debt(borrower) == POSITION_DEBT - amount
    assert cdp.collateral(borrower) == POSITION_COLLATERAL - paid
    assert cdp.balanceOf(borrower) == POSITION_DEBT  # the borrower's mUSD is untouched
    assert cdp.balanceOf(redeemer) == POSITION_DEBT - amount
    assert cdp.totalSupply() == supply - amount
    assert token.balanceOf(redeemer) == redeemer_tokens + paid


def test_redeem_emits_event(cdp, borrower_position, funded_liquidator):
    amount = 400 * ETH

    cdp.redeem(borrower_position, amount, 1, sender=funded_liquidator)
    logs = filter_logs(cdp, "Redeem")

    assert len(logs) == 1
    assert (logs[0].redeemer, logs[0].user) == (funded_liquidator, borrower_position)
    assert (logs[0].amount, logs[0].paid) == (amount, _redeemed(amount))


def test_fee_stays_with_borrower(cdp, borrower_position, funded_liquidator):
    """The borrower loses $400 of debt and $396 of collateral: they keep $4 of value."""
    amount = 400 * ETH
    paid = cdp.redeem(borrower_position, amount, 1, sender=funded_liquidator)

    assert amount - paid * 2000 == amount * redemption_fee(POSITION_RATIO) // PRECISION == 4 * ETH


def test_redeem_raises_collat_ratio(cdp, borrower_position, funded_liquidator):
    ratio = cdp.collat_ratio(borrower_position)

    cdp.redeem(borrower_position, 400 * ETH, 1, sender=funded_liquidator)

    assert cdp.collat_ratio(borrower_position) > ratio


def test_redeem_whole_debt(cdp, borrower_position, funded_liquidator):
    paid = cdp.redeem(borrower_position, POSITION_DEBT, 1, sender=funded_liquidator)

    assert cdp.debt(borrower_position) == 0
    assert cdp.debt_shares(borrower_position) == 0
    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL - paid


def test_redeem_at_min_ratio(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(to_feed_price(1500))
    assert cdp.collat_ratio(borrower_position) == MIN_COLLAT_RATIO

    paid = cdp.redeem(borrower_position, ETH, 1, sender=funded_liquidator)

    # At exactly 150% the fee is the 0.5% base.
    assert redemption_fee(MIN_COLLAT_RATIO) == REDEMPTION_FEE
    assert paid == _redeemed(ETH, MIN_COLLAT_RATIO, to_feed_price(1500))


def test_redeem_min_paid(cdp, borrower_position, funded_liquidator):
    paid = _redeemed(400 * ETH)

    with boa.reverts(dev="[cdp] slippage"):
        cdp.redeem(borrower_position, 400 * ETH, paid + 1, sender=funded_liquidator)

    assert cdp.redeem(borrower_position, 400 * ETH, paid, sender=funded_liquidator) == paid


def test_redeem_unhealthy_reverts(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(to_feed_price(1500) - 1)

    with boa.reverts(dev="[cdp] position unhealthy"):
        cdp.redeem(borrower_position, ETH, 1, sender=funded_liquidator)


def test_redeem_zero_reverts(cdp, borrower_position, funded_liquidator):
    with boa.reverts(dev="[cdp_erc20] amount must be greater than zero (0)."):
        cdp.redeem(borrower_position, 0, 1, sender=funded_liquidator)


def test_redeem_more_than_debt_reverts(cdp, borrower_position, funded_liquidator):
    cdp.transfer(funded_liquidator, POSITION_DEBT, sender=borrower_position)

    with boa.reverts(dev="[cdp] repay exceeds debt"):
        cdp.redeem(borrower_position, POSITION_DEBT + 1, 1, sender=funded_liquidator)


def test_redeem_debt_free_position_reverts(cdp, funded_borrower, funded_liquidator):
    """Debt-free positions read as healthy, but have nothing to redeem."""
    cdp.deposit(ETH, sender=funded_borrower)

    with boa.reverts(dev="[cdp] repay exceeds debt"):
        cdp.redeem(funded_borrower, ETH, 1, sender=funded_liquidator)


def test_redeem_without_musd_reverts(cdp, borrower_position, recipient):
    with boa.reverts(dev="[erc20] burn amount exceeds balance"):
        cdp.redeem(borrower_position, ETH, 1, sender=recipient)


def test_redeem_own_position(cdp, token, borrower_position):
    """Redeeming yourself is a repay-and-withdraw that pays the fee to yourself."""
    tokens = token.balanceOf(borrower_position)

    paid = cdp.redeem(borrower_position, 400 * ETH, 1, sender=borrower_position)

    assert cdp.debt(borrower_position) == POSITION_DEBT - 400 * ETH
    assert token.balanceOf(borrower_position) == tokens + paid
