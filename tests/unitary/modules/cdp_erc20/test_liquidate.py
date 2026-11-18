import boa
import pytest

from tests.utils.constants import (
    ETH,
    LIQUIDATION_PENALTY,
    LIQUIDATION_PRICE,
    MAX_UINT256,
    MIN_COLLAT_RATIO,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    PRECISION,
)
from tests.utils.helpers import filter_logs, held_collateral, liquidation, to_feed_price

# At $1400 the default position (1 token, 1000 mUSD) is at 140%: repaying
# 250 mUSD for $275 of collateral brings it back to exactly 150%. The 10 wei
# on top is `liquidate`'s rounding margin.
PARTIAL_PRICE = to_feed_price(1400)
PARTIAL_REPAY = 250 * ETH + 10
# At $900 the position is at 90%: its collateral covers 900 / 1.1 mUSD at 110%.
INSOLVENT_PRICE = to_feed_price(900)


# ================= Partial liquidation =================


def test_partial_liquidation_restores_min_ratio(
    cdp, token, oracle, borrower_position, funded_liquidator
):
    """Money Flow: liquidator mUSD → burned, 110% of it in borrower collateral → liquidator."""
    borrower, liquidator = borrower_position, funded_liquidator
    # ================= Capture initial state =================
    liquidator_tokens = token.balanceOf(liquidator)
    cdp_tokens = token.balanceOf(cdp.address)
    supply = cdp.totalSupply()
    oracle.set_answer(PARTIAL_PRICE)
    repaid, seized, _ = liquidation(POSITION_COLLATERAL, POSITION_DEBT, PARTIAL_PRICE, MAX_UINT256)
    assert repaid == PARTIAL_REPAY

    # ================= Execute =================
    assert cdp.liquidate(borrower, MAX_UINT256, sender=liquidator) == repaid

    # ================= Verify state and money flows =================
    assert cdp.debt(borrower) == POSITION_DEBT - repaid
    assert cdp.collateral(borrower) == POSITION_COLLATERAL - seized
    assert MIN_COLLAT_RATIO <= cdp.collat_ratio(borrower) < MIN_COLLAT_RATIO + 10**9
    assert cdp.balanceOf(liquidator) == POSITION_DEBT - repaid
    assert cdp.totalSupply() == supply - repaid
    assert token.balanceOf(liquidator) == liquidator_tokens + seized
    assert token.balanceOf(cdp.address) == cdp_tokens - seized
    assert token.balanceOf(cdp.address) == held_collateral(cdp, [borrower, liquidator])
    # The liquidator's bonus: $1.10 of collateral per $1 repaid.
    assert repaid * 11 // 10 - 1400 < seized * 1400 <= repaid * 11 // 10


def test_liquidate_emits_events(cdp, oracle, borrower_position, funded_liquidator):
    borrower, liquidator = borrower_position, funded_liquidator
    oracle.set_answer(PARTIAL_PRICE)
    _, seized, _ = liquidation(POSITION_COLLATERAL, POSITION_DEBT, PARTIAL_PRICE, MAX_UINT256)

    cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    logs = filter_logs(cdp, "Liquidate")
    # mUSD transfers only: the collateral token logs its own `Transfer`.
    transfers = [t for t in filter_logs(cdp, "Transfer") if t.address == cdp.address]

    assert len(logs) == 1
    assert (logs[0].liquidator, logs[0].user) == (liquidator, borrower)
    assert (logs[0].repaid, logs[0].seized, logs[0].written_off) == (PARTIAL_REPAY, seized, 0)
    assert len(transfers) == 1
    assert (transfers[0].sender, transfers[0].value) == (liquidator, PARTIAL_REPAY)


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

    with boa.reverts(dev="[cdp_erc20] max repay amount must be greater than zero (0)."):
        cdp.liquidate(borrower_position, 0, sender=funded_liquidator)


def test_self_liquidation(cdp, token, oracle, borrower_position):
    """An underwater borrower can liquidate themselves, keeping the bonus."""
    borrower = borrower_position
    borrower_tokens = token.balanceOf(borrower)
    oracle.set_answer(PARTIAL_PRICE)
    _, seized, _ = liquidation(POSITION_COLLATERAL, POSITION_DEBT, PARTIAL_PRICE, MAX_UINT256)

    cdp.liquidate(borrower, MAX_UINT256, sender=borrower)

    assert cdp.debt(borrower) == POSITION_DEBT - PARTIAL_REPAY
    assert token.balanceOf(borrower) == borrower_tokens + seized


# ================= Insolvent positions =================


def test_insolvent_position_is_closed_and_written_off(
    cdp, token, oracle, borrower_position, funded_liquidator
):
    borrower, liquidator = borrower_position, funded_liquidator
    liquidator_tokens = token.balanceOf(liquidator)
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
    assert token.balanceOf(liquidator) == liquidator_tokens + POSITION_COLLATERAL
    # No surplus to absorb it: the gap between supply and debt is bad debt.
    assert cdp.bad_debt() == written_off
    assert cdp.totalSupply() == cdp.debt(liquidator) + cdp.bad_debt()
    assert cdp.total_debt_shares() == cdp.debt_shares(liquidator)


@pytest.mark.parametrize("usd", [1000, 1050, 1099])
def test_covered_position_repays_whole_debt(
    cdp, token, oracle, borrower_position, funded_liquidator, usd
):
    """Between 100% and 110% the liquidator repays all of the debt for all of
    the collateral: the bonus shrinks to zero at 100% and nothing is written off."""
    borrower, liquidator = borrower_position, funded_liquidator
    liquidator_tokens = token.balanceOf(liquidator)
    oracle.set_answer(to_feed_price(usd))

    repaid = cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    log = filter_logs(cdp, "Liquidate")[0]

    assert repaid == POSITION_DEBT
    assert (log.repaid, log.seized, log.written_off) == (POSITION_DEBT, POSITION_COLLATERAL, 0)
    assert cdp.debt(borrower) == 0
    assert cdp.collateral(borrower) == 0
    assert cdp.bad_debt() == 0
    assert token.balanceOf(liquidator) == liquidator_tokens + POSITION_COLLATERAL
    assert cdp.totalSupply() == cdp.debt(liquidator)


def test_insolvent_requires_full_repay(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(INSOLVENT_PRICE)
    repaid, _, _ = liquidation(POSITION_COLLATERAL, POSITION_DEBT, INSOLVENT_PRICE, MAX_UINT256)

    with boa.reverts(dev="[cdp] repay too small"):
        cdp.liquidate(borrower_position, repaid - 1, sender=funded_liquidator)

    cdp.liquidate(borrower_position, repaid, sender=funded_liquidator)


def test_worthless_collateral_writes_off_everything(
    cdp, oracle, borrower_position, funded_liquidator
):
    """At $1e-8 a token is worth ~nothing: the liquidator repays dust and takes it all."""
    oracle.set_answer(1)

    repaid = cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)

    assert repaid < 10**10
    assert cdp.collateral(borrower_position) == 0
    assert cdp.bad_debt() == POSITION_DEBT - repaid


# ================= When liquidation is refused =================


def test_liquidate_healthy_reverts(cdp, borrower_position, funded_liquidator):
    with boa.reverts(dev="[cdp] position healthy"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)


def test_liquidate_at_exact_min_ratio_reverts(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(LIQUIDATION_PRICE)
    assert cdp.collat_ratio(borrower_position) == MIN_COLLAT_RATIO

    with boa.reverts(dev="[cdp] position healthy"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)


def test_liquidate_just_below_min_ratio(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(LIQUIDATION_PRICE - 1)

    repaid = cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)

    assert 0 < repaid < ETH
    assert cdp.collat_ratio(borrower_position) >= MIN_COLLAT_RATIO


def test_liquidate_debt_free_position_reverts(cdp, funded_borrower, funded_liquidator):
    cdp.deposit(ETH, sender=funded_borrower)

    with boa.reverts(dev="[cdp] position healthy"):
        cdp.liquidate(funded_borrower, MAX_UINT256, sender=funded_liquidator)


def test_liquidate_without_enough_musd_reverts(cdp, oracle, borrower_position, liquidator):
    oracle.set_answer(PARTIAL_PRICE)

    with boa.reverts(dev="[erc20] burn amount exceeds balance"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=liquidator)

    assert cdp.debt(borrower_position) == POSITION_DEBT


def test_liquidate_twice_reverts(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(PARTIAL_PRICE)
    cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)

    with boa.reverts(dev="[cdp] position healthy"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)


def test_liquidate_with_stale_price_reverts(cdp, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(PARTIAL_PRICE)
    boa.env.time_travel(seconds=cdp.ORACLE_TIMEOUT() + 1)

    with boa.reverts(dev="[cdp] stale price"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)


def test_liquidate_when_token_transfer_fails_reverts(
    cdp, token, oracle, borrower_position, funded_liquidator
):
    oracle.set_answer(PARTIAL_PRICE)
    token.set_return_false(True)

    with boa.reverts(dev="[cdp_erc20] transfer failed"):
        cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator)

    assert cdp.debt(borrower_position) == POSITION_DEBT
