import boa

from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    MIN_COLLAT_RATIO,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    MAX_REDEMPTION_FEE,
    PRECISION,
    REDEMPTION_FEE,
)
from tests.utils.helpers import filter_logs, redemption_fee, to_feed_price

# The default position's ratio at $2000.
POSITION_RATIO = 2 * PRECISION


def _redeemed_eth(amount: int, ratio: int = POSITION_RATIO, feed_price: int = ETH_USD_PRICE) -> int:
    """ETH paid for `amount` mUSD from a position at `ratio` (mirrors `redeem`)."""
    return amount * (PRECISION - redemption_fee(ratio)) // (feed_price * 10**10)


def test_redeem(cdp, borrower_position, funded_liquidator):
    """Money Flow: redeemer mUSD → burned, $1 of the borrower's ETH less 1% → redeemer."""
    borrower, redeemer = borrower_position, funded_liquidator
    redeemer_eth = boa.env.get_balance(redeemer)
    supply = cdp.totalSupply()
    amount = 400 * ETH
    eth = _redeemed_eth(amount)

    assert cdp.redeem(borrower, amount, 1, sender=redeemer) == eth

    assert eth == 198 * ETH // 1000  # $400 at $2000, less 1% at 200%
    assert cdp.debt(borrower) == POSITION_DEBT - amount
    assert cdp.collateral(borrower) == POSITION_COLLATERAL - eth
    assert cdp.balanceOf(borrower) == POSITION_DEBT  # the borrower's mUSD is untouched
    assert cdp.balanceOf(redeemer) == POSITION_DEBT - amount
    assert cdp.totalSupply() == supply - amount
    assert boa.env.get_balance(redeemer) == redeemer_eth + eth


def test_fee_stays_with_borrower(cdp, borrower_position, funded_liquidator):
    """The borrower loses $400 of debt and $396 of ETH: they keep $4 of value."""
    amount = 400 * ETH
    eth = cdp.redeem(borrower_position, amount, 1, sender=funded_liquidator)

    kept = amount - eth * 2000
    assert kept == amount * redemption_fee(POSITION_RATIO) // PRECISION == 4 * ETH


def test_redeem_fee_at_min_ratio(cdp, oracle, borrower_position, funded_liquidator):
    """At exactly 150% the fee is the 0.5% base."""
    oracle.set_answer(to_feed_price(1500))
    assert cdp.collat_ratio(borrower_position) == MIN_COLLAT_RATIO
    assert redemption_fee(MIN_COLLAT_RATIO) == REDEMPTION_FEE

    eth = cdp.redeem(borrower_position, 300 * ETH, 1, sender=funded_liquidator)

    assert eth == _redeemed_eth(300 * ETH, MIN_COLLAT_RATIO, to_feed_price(1500))
    assert eth == 199 * ETH // 1000  # $300 at $1500, less 0.5%


def test_redeem_fee_rises_with_ratio(cdp, borrower_position, funded_liquidator, recipient):
    """A 400% position pays the redeemer less per mUSD than a 200% one."""
    cdp.deposit(value=2 * ETH, sender=recipient)
    cdp.mint(POSITION_DEBT, sender=recipient)
    assert cdp.collat_ratio(recipient) == 4 * PRECISION

    risky = cdp.redeem(borrower_position, 400 * ETH, 1, sender=funded_liquidator)
    safe = cdp.redeem(recipient, 400 * ETH, 1, sender=funded_liquidator)

    assert risky == _redeemed_eth(400 * ETH)  # 1% fee
    assert safe == _redeemed_eth(400 * ETH, 4 * PRECISION)  # 3% fee
    assert safe < risky


def test_redeem_fee_is_capped(cdp, borrower_position, funded_liquidator):
    """The liquidator's 2000% position pays the 5% cap, not 19%."""
    assert cdp.collat_ratio(funded_liquidator) == 20 * PRECISION

    eth = cdp.redeem(funded_liquidator, 400 * ETH, 1, sender=borrower_position)

    assert eth == 400 * ETH * (PRECISION - MAX_REDEMPTION_FEE) // (ETH_USD_PRICE * 10**10)
    assert eth == 19 * ETH // 100  # $400 at $2000, less 5%


def test_redeem_min_paid(cdp, borrower_position, funded_liquidator):
    eth = _redeemed_eth(400 * ETH)

    with boa.reverts(dev="[cdp] slippage"):
        cdp.redeem(borrower_position, 400 * ETH, eth + 1, sender=funded_liquidator)

    assert cdp.redeem(borrower_position, 400 * ETH, eth, sender=funded_liquidator) == eth


def test_redeem_raises_collat_ratio(cdp, borrower_position, funded_liquidator):
    ratio = cdp.collat_ratio(borrower_position)

    cdp.redeem(borrower_position, 400 * ETH, 1, sender=funded_liquidator)

    assert cdp.collat_ratio(borrower_position) > ratio


def test_redeem_whole_debt(cdp, borrower_position, funded_liquidator):
    eth = cdp.redeem(borrower_position, POSITION_DEBT, 1, sender=funded_liquidator)

    assert cdp.debt(borrower_position) == 0
    assert cdp.debt_shares(borrower_position) == 0
    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL - eth


def test_redeem_emits_event(cdp, borrower_position, funded_liquidator):
    eth = cdp.redeem(borrower_position, 400 * ETH, 1, sender=funded_liquidator)
    log = filter_logs(cdp, "Redeem")[0]

    assert (log.redeemer, log.user) == (funded_liquidator, borrower_position)
    assert (log.amount, log.paid) == (400 * ETH, eth)


def test_redeem_more_than_debt_reverts(cdp, borrower_position, funded_liquidator, recipient):
    cdp.deposit(value=10 * ETH, sender=recipient)
    cdp.mint(POSITION_DEBT, sender=recipient)
    cdp.transfer(funded_liquidator, POSITION_DEBT, sender=recipient)

    with boa.reverts(dev="[cdp] repay exceeds debt"):
        cdp.redeem(borrower_position, POSITION_DEBT + 1, 1, sender=funded_liquidator)


def test_redeem_unhealthy_position_reverts(
    cdp, oracle, borrower_position, funded_liquidator
):
    """Positions under 150% are for liquidators, at a 10% bonus, not redeemers."""
    oracle.set_answer(to_feed_price(1400))
    assert cdp.collat_ratio(borrower_position) < MIN_COLLAT_RATIO

    with boa.reverts(dev="[cdp] position unhealthy"):
        cdp.redeem(borrower_position, ETH, 1, sender=funded_liquidator)


def test_redeem_debt_free_position_reverts(cdp, borrower, funded_liquidator):
    cdp.deposit(value=ETH, sender=borrower)

    with boa.reverts(dev="[cdp] repay exceeds debt"):
        cdp.redeem(borrower, ETH, 1, sender=funded_liquidator)


def test_redeem_zero_reverts(cdp, borrower_position, funded_liquidator):
    with boa.reverts(dev="[cdp_native] amount must be greater than zero (0)."):
        cdp.redeem(borrower_position, 0, 1, sender=funded_liquidator)


def test_redeem_without_enough_musd_reverts(cdp, borrower_position, liquidator):
    with boa.reverts(dev="[erc20] burn amount exceeds balance"):
        cdp.redeem(borrower_position, ETH, 1, sender=liquidator)


def test_redeem_with_stale_price_reverts(cdp, borrower_position, funded_liquidator):
    boa.env.time_travel(seconds=cdp.ORACLE_TIMEOUT() + 1)

    with boa.reverts(dev="[cdp] stale price"):
        cdp.redeem(borrower_position, ETH, 1, sender=funded_liquidator)


def test_redeem_own_position(cdp, borrower_position):
    """Redeeming yourself is a repay that pays the fee to yourself."""
    cdp.redeem(borrower_position, POSITION_DEBT, 1, sender=borrower_position)

    assert cdp.debt(borrower_position) == 0
    assert cdp.balanceOf(borrower_position) == 0
