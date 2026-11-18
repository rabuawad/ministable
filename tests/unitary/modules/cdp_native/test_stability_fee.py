import boa
import pytest

from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    MAX_STABILITY_FEE,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    PRECISION,
    SWAP_FEE,
    YEAR,
)
from tests.utils.helpers import deploy_cdp_native, filter_logs


def _index_after(seconds: int, fee: int = MAX_STABILITY_FEE) -> int:
    return PRECISION + PRECISION * fee * seconds // PRECISION


def _debt_after(principal: int, seconds: int) -> int:
    """Debt of a position that minted `principal` at index 1e18 (mirrors `_debt`)."""
    return -(-principal * _index_after(seconds) // PRECISION)


def _wait(oracle, seconds: int):
    """Let time pass, keeping the oracle fresh."""
    boa.env.time_travel(seconds=seconds)
    oracle.set_answer(ETH_USD_PRICE)


@pytest.fixture
def fee_cdp(oracle):
    oracle.set_answer(ETH_USD_PRICE)
    return deploy_cdp_native(oracle.address, fee=MAX_STABILITY_FEE)


@pytest.fixture
def fee_position(fee_cdp, borrower):
    fee_cdp.deposit(value=POSITION_COLLATERAL, sender=borrower)
    fee_cdp.mint(POSITION_DEBT, sender=borrower)
    return borrower


def test_fee_above_cap_reverts(oracle):
    with boa.reverts(dev="[cdp] stability fee too high"):
        deploy_cdp_native(oracle.address, fee=MAX_STABILITY_FEE + 1)


def test_parameters(fee_cdp):
    assert fee_cdp.STABILITY_FEE() == MAX_STABILITY_FEE
    assert fee_cdp.MAX_STABILITY_FEE() == MAX_STABILITY_FEE
    assert fee_cdp.rate_index() == PRECISION


def test_debt_grows_with_time(fee_cdp, oracle, fee_position):
    _wait(oracle, YEAR)

    # The view includes interest that hasn't been accrued yet.
    assert fee_cdp.debt(fee_position) == _debt_after(POSITION_DEBT, YEAR)
    assert fee_cdp.debt(fee_position) > POSITION_DEBT * 109 // 100


def test_accrual_mints_interest_to_surplus(fee_cdp, oracle, fee_position):
    _wait(oracle, YEAR)
    fee_cdp.mint(0, sender=fee_position)
    logs = filter_logs(fee_cdp, "Accrue")

    interest = fee_cdp.debt(fee_position) - POSITION_DEBT
    assert fee_cdp.rate_index() == _index_after(YEAR)
    assert interest - 1 <= fee_cdp.surplus() <= interest
    assert fee_cdp.balanceOf(fee_cdp.address) == fee_cdp.surplus()
    assert logs[0].amount == fee_cdp.surplus()


def test_debt_free_position_does_not_accrue(fee_cdp, oracle, borrower):
    fee_cdp.deposit(value=ETH, sender=borrower)
    _wait(oracle, YEAR)
    fee_cdp.withdraw(ETH, sender=borrower)

    assert fee_cdp.debt(borrower) == 0
    assert fee_cdp.surplus() == 0


def test_interest_lowers_collat_ratio(fee_cdp, oracle, fee_position):
    ratio = fee_cdp.collat_ratio(fee_position)
    _wait(oracle, YEAR)

    assert fee_cdp.collat_ratio(fee_position) < ratio


def test_full_repay_with_surplus_bought(fee_cdp, oracle, fee_position, recipient):
    """Interest is minted to the surplus, so a borrower buys it there to close out.
    A second borrower's interest keeps the surplus above what the first one
    buys: purchases move in whole wei of ETH, less the swap fee, so a buyer
    can overshoot the exact amount by a few wei."""
    borrower = fee_position
    fee_cdp.deposit(value=POSITION_COLLATERAL, sender=recipient)
    fee_cdp.mint(POSITION_DEBT, sender=recipient)
    _wait(oracle, YEAR)
    fee_cdp.mint(0, sender=borrower)
    debt = fee_cdp.debt(borrower)
    missing = debt - fee_cdp.balanceOf(borrower)

    # The surplus is sold less the swap fee, so pay for a little more.
    usd = -(-missing * PRECISION // (PRECISION - SWAP_FEE))
    eth = -(-usd * PRECISION // (ETH_USD_PRICE * 10**10))
    fee_cdp.buy_surplus(value=eth, sender=borrower)
    fee_cdp.burn(debt, sender=borrower)
    fee_cdp.withdraw(POSITION_COLLATERAL, sender=borrower)

    assert fee_cdp.debt(borrower) == 0
    assert fee_cdp.debt_shares(borrower) == 0
    assert fee_cdp.total_debt_shares() == fee_cdp.debt_shares(recipient)
    assert fee_cdp.collateral(borrower) == 0
    assert fee_cdp.reserve() == eth
    assert boa.env.get_balance(fee_cdp.address) == eth + POSITION_COLLATERAL


def test_partial_repay(fee_cdp, oracle, fee_position):
    _wait(oracle, YEAR)
    debt = fee_cdp.debt(fee_position)

    fee_cdp.burn(POSITION_DEBT // 2, sender=fee_position)

    remaining = fee_cdp.debt(fee_position)
    # Partial repays round the shares removed down, never in the borrower's favour.
    assert debt - POSITION_DEBT // 2 <= remaining <= debt - POSITION_DEBT // 2 + 1


def test_burn_more_than_debt_reverts(fee_cdp, fee_position):
    with boa.reverts(dev="[cdp] repay exceeds debt"):
        fee_cdp.burn(POSITION_DEBT + 1, sender=fee_position)


def test_buy_surplus(fee_cdp, oracle, fee_position, recipient):
    _wait(oracle, YEAR)
    fee_cdp.mint(0, sender=fee_position)
    surplus = fee_cdp.surplus()
    eth = ETH // 100  # $20 at $2000

    out = fee_cdp.buy_surplus(value=eth, sender=recipient)
    log = filter_logs(fee_cdp, "BuySurplus")[0]

    # $20 of mUSD, less the 0.5% swap fee.
    assert out == 20 * ETH * (PRECISION - SWAP_FEE) // PRECISION
    assert fee_cdp.balanceOf(recipient) == out
    assert fee_cdp.surplus() == surplus - out
    assert fee_cdp.reserve() == eth
    assert (log.buyer, log.paid, log.amount) == (recipient, eth, out)


def test_buy_more_than_surplus_reverts(fee_cdp, oracle, fee_position, recipient):
    _wait(oracle, YEAR)

    with boa.reverts(dev="[cdp] not enough surplus"):
        fee_cdp.buy_surplus(value=ETH, sender=recipient)


def test_buy_nothing_reverts(fee_cdp, recipient):
    with boa.reverts(dev="[cdp] zero purchase"):
        fee_cdp.buy_surplus(value=0, sender=recipient)


def test_interest_free_deployment_never_accrues(cdp, oracle, borrower_position):
    _wait(oracle, YEAR)
    cdp.mint(0, sender=borrower_position)

    assert cdp.debt(borrower_position) == POSITION_DEBT
    assert cdp.surplus() == 0
