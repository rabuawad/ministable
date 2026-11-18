import boa
import pytest

from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    LIQUIDATION_PENALTY,
    LIQUIDATION_PRICE,
    MAX_STABILITY_FEE,
    MAX_UINT256,
    MIN_COLLAT_RATIO,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    PRECISION,
    SWAP_FEE,
    YEAR,
)
from tests.utils.helpers import (
    deploy_cdp_native,
    filter_logs,
    liquidation,
    max_mintable,
    to_feed_price,
)

# At $1400 the default position (1 ETH, 1000 mUSD) is at 140%: repaying
# 250 mUSD for 275 $ of ETH brings it back to exactly 150%. The 10 wei
# on top is `liquidate`'s rounding margin.
PARTIAL_PRICE = to_feed_price(1400)
PARTIAL_REPAY = 250 * ETH + 10
# At $1050 the position is at 105%: its ETH covers the debt, but not 110% of it.
COVERED_PRICE = to_feed_price(1050)
# At $900 the position is at 90%: its ETH covers 900 / 1.1 mUSD at 110%.
INSOLVENT_PRICE = to_feed_price(900)


# ================= Partial liquidation =================


def test_partial_liquidation_restores_min_ratio(
    cdp, oracle, borrower_position, funded_liquidator
):
    """Money Flow: liquidator mUSD → burned, 110% of it in borrower ETH → liquidator."""
    borrower, liquidator = borrower_position, funded_liquidator
    liquidator_eth = boa.env.get_balance(liquidator)
    supply = cdp.totalSupply()
    oracle.set_answer(PARTIAL_PRICE)
    repaid, seized, _ = liquidation(POSITION_COLLATERAL, POSITION_DEBT, PARTIAL_PRICE, MAX_UINT256)
    assert repaid == PARTIAL_REPAY

    assert cdp.liquidate(borrower, MAX_UINT256, sender=liquidator) == repaid

    assert cdp.debt(borrower) == POSITION_DEBT - repaid
    assert cdp.collateral(borrower) == POSITION_COLLATERAL - seized
    assert cdp.collat_ratio(borrower) >= MIN_COLLAT_RATIO
    assert cdp.collat_ratio(borrower) < MIN_COLLAT_RATIO + 10**9
    assert cdp.balanceOf(liquidator) == POSITION_DEBT - repaid
    assert cdp.totalSupply() == supply - repaid
    assert boa.env.get_balance(liquidator) == liquidator_eth + seized
    # The liquidator's bonus: $1.10 of ETH per $1 repaid.
    assert repaid * 11 // 10 - 1400 < seized * 1400 <= repaid * 11 // 10


def test_over_ask_is_capped(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(PARTIAL_PRICE)

    cdp.liquidate(borrower_position, POSITION_DEBT, sender=funded_liquidator)

    assert cdp.debt(borrower_position) == POSITION_DEBT - PARTIAL_REPAY


def test_small_repay_improves_ratio(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(PARTIAL_PRICE)
    ratio = cdp.collat_ratio(borrower_position)

    cdp.liquidate(borrower_position, 100 * ETH, sender=funded_liquidator)

    assert cdp.debt(borrower_position) == POSITION_DEBT - 100 * ETH
    assert ratio < cdp.collat_ratio(borrower_position) < MIN_COLLAT_RATIO

    # Still unhealthy, so anyone can finish the job.
    cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)
    assert cdp.collat_ratio(borrower_position) >= MIN_COLLAT_RATIO


def test_zero_repay_reverts(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(PARTIAL_PRICE)

    with boa.reverts(dev="[cdp_native] max repay amount must be greater than zero (0)."):
        cdp.liquidate(borrower_position, 0, sender=funded_liquidator)


def test_liquidate_emits_events(cdp, oracle, borrower_position, funded_liquidator):
    borrower, liquidator = borrower_position, funded_liquidator
    oracle.set_answer(PARTIAL_PRICE)
    _, seized, _ = liquidation(POSITION_COLLATERAL, POSITION_DEBT, PARTIAL_PRICE, MAX_UINT256)

    cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    logs = filter_logs(cdp, "Liquidate")
    transfer_logs = filter_logs(cdp, "Transfer")

    assert len(logs) == 1
    assert (logs[0].liquidator, logs[0].user) == (liquidator, borrower)
    assert (logs[0].repaid, logs[0].seized, logs[0].written_off) == (PARTIAL_REPAY, seized, 0)
    assert len(transfer_logs) == 1
    assert transfer_logs[0].sender == liquidator
    assert transfer_logs[0].value == PARTIAL_REPAY


def test_liquidate_leaves_liquidator_position_untouched(
    cdp, oracle, borrower_position, funded_liquidator
):
    liquidator = funded_liquidator
    collateral, debt = cdp.collateral(liquidator), cdp.debt(liquidator)
    oracle.set_answer(PARTIAL_PRICE)

    cdp.liquidate(borrower_position, MAX_UINT256, sender=liquidator)

    assert cdp.collateral(liquidator) == collateral
    assert cdp.debt(liquidator) == debt


# ================= Insolvent positions and bad debt =================


def test_insolvent_position_is_closed_and_written_off(
    cdp, oracle, borrower_position, funded_liquidator
):
    borrower, liquidator = borrower_position, funded_liquidator
    liquidator_eth = boa.env.get_balance(liquidator)
    oracle.set_answer(INSOLVENT_PRICE)
    repaid, seized, written_off = liquidation(
        POSITION_COLLATERAL, POSITION_DEBT, INSOLVENT_PRICE, MAX_UINT256
    )
    assert seized == POSITION_COLLATERAL
    assert repaid == 900 * ETH * PRECISION // LIQUIDATION_PENALTY

    cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    log = filter_logs(cdp, "Liquidate")[0]

    assert (log.repaid, log.seized, log.written_off) == (repaid, seized, written_off)
    assert cdp.debt(borrower) == 0
    assert cdp.debt_shares(borrower) == 0
    assert cdp.collateral(borrower) == 0
    assert boa.env.get_balance(liquidator) == liquidator_eth + POSITION_COLLATERAL
    # No surplus to absorb it: the gap between supply and debt is bad debt.
    assert cdp.bad_debt() == written_off
    # Every mUSD is still owed by a position or recorded as bad debt.
    assert cdp.totalSupply() == cdp.debt(liquidator) + cdp.bad_debt()


@pytest.mark.parametrize("usd", [1000, 1050, 1099])
def test_covered_position_repays_whole_debt(
    cdp, oracle, borrower_position, funded_liquidator, usd
):
    """Between 100% and 110% the liquidator repays all of the debt for all of
    the ETH: the bonus shrinks to zero at 100% and nothing is written off."""
    borrower, liquidator = borrower_position, funded_liquidator
    liquidator_eth = boa.env.get_balance(liquidator)
    oracle.set_answer(to_feed_price(usd))

    repaid = cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    log = filter_logs(cdp, "Liquidate")[0]

    assert repaid == POSITION_DEBT
    assert (log.repaid, log.seized, log.written_off) == (POSITION_DEBT, POSITION_COLLATERAL, 0)
    assert cdp.debt(borrower) == 0
    assert cdp.collateral(borrower) == 0
    assert cdp.bad_debt() == 0
    assert boa.env.get_balance(liquidator) == liquidator_eth + POSITION_COLLATERAL
    assert cdp.totalSupply() == cdp.debt(liquidator)


def test_covered_position_requires_full_repay(
    cdp, oracle, borrower_position, funded_liquidator
):
    oracle.set_answer(COVERED_PRICE)

    with boa.reverts(dev="[cdp] repay too small"):
        cdp.liquidate(borrower_position, POSITION_DEBT - 1, sender=funded_liquidator)

    cdp.liquidate(borrower_position, POSITION_DEBT, sender=funded_liquidator)


def test_insolvent_requires_full_repay(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(INSOLVENT_PRICE)
    repaid, _, _ = liquidation(POSITION_COLLATERAL, POSITION_DEBT, INSOLVENT_PRICE, MAX_UINT256)

    with boa.reverts(dev="[cdp] repay too small"):
        cdp.liquidate(borrower_position, repaid - 1, sender=funded_liquidator)

    cdp.liquidate(borrower_position, repaid, sender=funded_liquidator)


# ================= Surplus and reserve as a backstop =================


@pytest.fixture
def fee_cdp(oracle, borrower, liquidator, recipient):
    """A 10%-a-year deployment where `recipient` runs a large, safe position
    for a year, building up a surplus, and `borrower` holds the default position."""
    oracle.set_answer(ETH_USD_PRICE)
    cdp = deploy_cdp_native(oracle.address, fee=MAX_STABILITY_FEE)
    cdp.deposit(value=20 * ETH, sender=recipient)
    cdp.mint(10_000 * ETH, sender=recipient)
    cdp.transfer(liquidator, 2_000 * ETH, sender=recipient)
    cdp.deposit(value=POSITION_COLLATERAL, sender=borrower)
    cdp.mint(POSITION_DEBT, sender=borrower)
    return cdp


def _wait(oracle, seconds, price=ETH_USD_PRICE):
    boa.env.time_travel(seconds=seconds)
    oracle.set_answer(price)


def test_surplus_absorbs_bad_debt(fee_cdp, oracle, borrower, liquidator):
    _wait(oracle, YEAR, INSOLVENT_PRICE)
    fee_cdp.mint(0, sender=liquidator)
    surplus = fee_cdp.surplus()
    assert surplus > 1000 * ETH  # ~10% of 11,000 mUSD

    fee_cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    written_off = filter_logs(fee_cdp, "Liquidate")[0].written_off
    settled = filter_logs(fee_cdp, "Settle")[0].amount

    assert written_off > 0
    assert settled == written_off
    assert fee_cdp.bad_debt() == 0
    assert fee_cdp.surplus() == surplus - written_off


def test_later_interest_pays_down_bad_debt(fee_cdp, oracle, borrower, liquidator):
    oracle.set_answer(INSOLVENT_PRICE)
    fee_cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    bad_debt = fee_cdp.bad_debt()
    assert bad_debt > 0
    assert fee_cdp.surplus() == 0

    _wait(oracle, YEAR // 12, INSOLVENT_PRICE)
    fee_cdp.mint(0, sender=liquidator)  # any accruing call settles

    assert fee_cdp.bad_debt() < bad_debt
    assert fee_cdp.surplus() == 0


def test_cover_bad_debt_from_reserve(fee_cdp, oracle, borrower, liquidator, recipient):
    # Interest is sold for ETH, filling the reserve.
    _wait(oracle, YEAR)
    fee_cdp.mint(0, sender=recipient)
    eth_paid = fee_cdp.surplus() * PRECISION // (ETH_USD_PRICE * 10**10)
    fee_cdp.buy_surplus(value=eth_paid, sender=recipient)
    reserve = fee_cdp.reserve()

    # Then a position goes insolvent with no surplus left to absorb it.
    oracle.set_answer(INSOLVENT_PRICE)
    fee_cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    bad_debt = fee_cdp.bad_debt()
    assert bad_debt > 0

    liquidator_eth = boa.env.get_balance(liquidator)
    eth = fee_cdp.cover_bad_debt(bad_debt, sender=liquidator)
    log = filter_logs(fee_cdp, "CoverBadDebt")[0]

    # The 0.5% swap fee stays in the reserve.
    assert eth == bad_debt * (PRECISION - SWAP_FEE) // (INSOLVENT_PRICE * 10**10)
    assert (log.caller, log.amount, log.paid) == (liquidator, bad_debt, eth)
    assert fee_cdp.bad_debt() == 0
    assert fee_cdp.reserve() == reserve - eth
    assert boa.env.get_balance(liquidator) == liquidator_eth + eth


def test_cover_more_than_bad_debt_reverts(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(INSOLVENT_PRICE)
    cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)

    with boa.reverts(dev="[cdp] cover exceeds bad debt"):
        cdp.cover_bad_debt(cdp.bad_debt() + 1, sender=funded_liquidator)


def test_cover_without_reserve_reverts(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(INSOLVENT_PRICE)
    cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)

    with boa.reverts(dev="[cdp] not enough reserve"):
        cdp.cover_bad_debt(cdp.bad_debt(), sender=funded_liquidator)


def test_cover_zero_reverts(cdp, funded_liquidator):
    with boa.reverts(dev="[cdp_native] amount must be greater than zero (0)."):
        cdp.cover_bad_debt(0, sender=funded_liquidator)


# ================= When liquidation is refused =================


def test_liquidate_at_exact_min_ratio_reverts(
    cdp, oracle, borrower_position, funded_liquidator
):
    oracle.set_answer(LIQUIDATION_PRICE)
    assert cdp.collat_ratio(borrower_position) == MIN_COLLAT_RATIO

    with boa.reverts(dev="[cdp] position healthy"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)


def test_liquidate_just_below_min_ratio(
    cdp, oracle, borrower_position, funded_liquidator
):
    oracle.set_answer(LIQUIDATION_PRICE - 1)

    repaid = cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)

    assert 0 < repaid < ETH
    assert cdp.collat_ratio(borrower_position) >= MIN_COLLAT_RATIO


def test_rounding_cannot_leave_position_below_min_ratio(oracle, borrower, liquidator):
    """Found by the stateful fuzzer: with interest accruing, the minimal
    repay once left the position at 150% minus 1 wei once its collateral
    value and its remaining debt shares were rounded."""
    oracle.set_answer(ETH_USD_PRICE)
    cdp = deploy_cdp_native(oracle.address, fee=MAX_STABILITY_FEE)
    cdp.deposit(value=10 * ETH, sender=liquidator)
    cdp.mint(POSITION_DEBT, sender=liquidator)

    price = ETH_USD_PRICE * 9_999 // 10_000 * 8_865 // 10_000
    oracle.set_answer(price)
    collateral = 50 * ETH - 1
    cdp.deposit(value=collateral, sender=borrower)
    # Share rounding can push the exact limit one wei over; step down.
    amount = max_mintable(collateral, price)
    while True:
        try:
            cdp.mint(amount, sender=borrower)
            break
        except boa.BoaError:
            amount -= 1

    _wait(oracle, 1, price)
    assert cdp.collat_ratio(borrower) < MIN_COLLAT_RATIO

    cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)

    assert cdp.collat_ratio(borrower) >= MIN_COLLAT_RATIO


def test_liquidate_healthy_reverts(cdp, borrower_position, funded_liquidator):
    with boa.reverts(dev="[cdp] position healthy"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)


def test_liquidate_debt_free_position_reverts(cdp, borrower, funded_liquidator):
    cdp.deposit(value=ETH, sender=borrower)

    with boa.reverts(dev="[cdp] position healthy"):
        cdp.liquidate(borrower, MAX_UINT256, sender=funded_liquidator)


def test_liquidate_without_enough_musd_reverts(
    cdp, oracle, borrower_position, liquidator
):
    oracle.set_answer(PARTIAL_PRICE)

    with boa.reverts(dev="[erc20] burn amount exceeds balance"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=liquidator)

    assert cdp.debt(borrower_position) == POSITION_DEBT


def test_liquidate_twice_reverts(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(PARTIAL_PRICE)
    cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)

    with boa.reverts(dev="[cdp] position healthy"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)


def test_liquidate_with_stale_price_reverts(
    cdp, oracle, borrower_position, funded_liquidator
):
    oracle.set_answer(PARTIAL_PRICE)
    boa.env.time_travel(seconds=cdp.ORACLE_TIMEOUT() + 1)

    with boa.reverts(dev="[cdp] stale price"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)


def test_self_liquidation(cdp, oracle, borrower_position):
    """An underwater borrower can liquidate themselves, keeping the bonus."""
    borrower = borrower_position
    borrower_eth = boa.env.get_balance(borrower)
    oracle.set_answer(PARTIAL_PRICE)
    _, seized, _ = liquidation(POSITION_COLLATERAL, POSITION_DEBT, PARTIAL_PRICE, MAX_UINT256)

    cdp.liquidate(borrower, MAX_UINT256, sender=borrower)

    assert cdp.debt(borrower) == POSITION_DEBT - PARTIAL_REPAY
    assert cdp.balanceOf(borrower) == POSITION_DEBT - PARTIAL_REPAY
    assert boa.env.get_balance(borrower) == borrower_eth + seized
