import boa
import pytest

from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    MAX_STABILITY_FEE,
    MAX_UINT256,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    PRECISION,
    SWAP_FEE,
    YEAR,
)
from tests.utils.helpers import (
    deploy_cdp_erc20,
    filter_logs,
    fund,
    held_collateral,
    price_scaled,
    to_feed_price,
)

# At $900 the default position (1 token, 1000 mUSD) is at 90%.
INSOLVENT_PRICE = to_feed_price(900)


def _index_after(seconds: int) -> int:
    return PRECISION + PRECISION * MAX_STABILITY_FEE * seconds // PRECISION


def _wait(oracle, seconds: int, price: int = ETH_USD_PRICE):
    """Let time pass, keeping the oracle fresh."""
    boa.env.time_travel(seconds=seconds)
    oracle.set_answer(price)


def _cost(amount: int, feed_price: int = ETH_USD_PRICE) -> int:
    """Collateral that buys `amount` mUSD of surplus at `feed_price`, after
    the swap fee, rounded down."""
    return amount * PRECISION // (PRECISION - SWAP_FEE) * PRECISION // price_scaled(feed_price)


def _bought(paid: int, feed_price: int = ETH_USD_PRICE) -> int:
    """mUSD that `paid` collateral buys from the surplus (mirrors `_buy_surplus`)."""
    return paid * price_scaled(feed_price) // PRECISION * (PRECISION - SWAP_FEE) // PRECISION


@pytest.fixture
def fee_cdp(token, oracle, borrower, liquidator, recipient):
    """A 10%-a-year deployment where `recipient` runs a large, safe position,
    `liquidator` holds 2000 mUSD and `borrower` holds the default position."""
    oracle.set_answer(ETH_USD_PRICE)
    cdp = deploy_cdp_erc20(token.address, oracle.address, fee=MAX_STABILITY_FEE)
    for account in (borrower, liquidator, recipient):
        fund(token, cdp, account)
    cdp.deposit(20 * ETH, sender=recipient)
    cdp.mint(10_000 * ETH, sender=recipient)
    cdp.transfer(liquidator, 2_000 * ETH, sender=recipient)
    cdp.deposit(POSITION_COLLATERAL, sender=borrower)
    cdp.mint(POSITION_DEBT, sender=borrower)
    return cdp


@pytest.fixture
def surplus_cdp(fee_cdp, oracle, recipient):
    """`fee_cdp` a year later, with the interest accrued to the surplus."""
    _wait(oracle, YEAR)
    fee_cdp.mint(0, sender=recipient)
    return fee_cdp


# ================= Interest =================


def test_debt_grows_with_time(fee_cdp, oracle, borrower):
    _wait(oracle, YEAR)

    # The view includes interest that hasn't been accrued yet.
    assert fee_cdp.debt(borrower) == -(-POSITION_DEBT * _index_after(YEAR) // PRECISION)
    assert fee_cdp.debt(borrower) > POSITION_DEBT * 109 // 100


def test_accrual_mints_interest_to_surplus(fee_cdp, oracle, borrower):
    _wait(oracle, YEAR)

    fee_cdp.mint(0, sender=borrower)
    logs = filter_logs(fee_cdp, "Accrue")

    assert fee_cdp.rate_index() == _index_after(YEAR)
    assert fee_cdp.last_accrual() == boa.env.evm.patch.timestamp
    assert len(logs) == 1
    assert logs[0].amount == fee_cdp.surplus()
    assert fee_cdp.surplus() == fee_cdp.balanceOf(fee_cdp.address)
    # 10% of the 11,000 mUSD owed, less share rounding.
    assert 1099 * ETH < fee_cdp.surplus() <= 1100 * ETH


def test_no_debt_accrues_nothing(token, oracle, borrower):
    cdp = deploy_cdp_erc20(token.address, oracle.address, fee=MAX_STABILITY_FEE)
    fund(token, cdp, borrower)
    cdp.deposit(ETH, sender=borrower)
    _wait(oracle, YEAR)

    cdp.mint(0, sender=borrower)

    assert cdp.surplus() == 0
    assert filter_logs(cdp, "Accrue") == []


def test_supply_matches_debt(surplus_cdp, borrower, recipient):
    """Interest is minted to the surplus as it accrues, so every mUSD,
    surplus included, is owed by some position."""
    debts = surplus_cdp.debt(borrower) + surplus_cdp.debt(recipient)
    supply = surplus_cdp.totalSupply()

    assert surplus_cdp.surplus() > 0
    # Debts round up per position, so they may exceed supply by a wei each.
    assert supply <= debts <= supply + 2


# ================= Buying the surplus =================


def test_buy_surplus(surplus_cdp, token, recipient):
    """Money Flow: buyer collateral → reserve, surplus mUSD → buyer."""
    cdp, buyer = surplus_cdp, recipient
    surplus = cdp.surplus()
    buyer_tokens, buyer_musd = token.balanceOf(buyer), cdp.balanceOf(buyer)
    paid = _cost(500 * ETH)

    bought = cdp.buy_surplus(paid, sender=buyer)
    log = filter_logs(cdp, "BuySurplus")[0]

    assert bought == _bought(paid)
    assert (log.buyer, log.paid, log.amount) == (buyer, paid, bought)
    assert cdp.reserve() == paid
    assert cdp.surplus() == surplus - bought
    assert cdp.balanceOf(buyer) == buyer_musd + bought
    assert token.balanceOf(buyer) == buyer_tokens - paid


def test_buy_whole_surplus(surplus_cdp, recipient):
    paid = _cost(surplus_cdp.surplus())

    surplus_cdp.buy_surplus(paid, sender=recipient)

    # Purchases move in whole base units, so less than one unit's worth is left.
    assert surplus_cdp.surplus() < price_scaled(ETH_USD_PRICE) // PRECISION + 2


def test_buy_more_than_surplus_reverts(surplus_cdp, recipient):
    # $2 more than the whole surplus.
    paid = _cost(surplus_cdp.surplus()) + ETH // 1000

    with boa.reverts(dev="[cdp] not enough surplus"):
        surplus_cdp.buy_surplus(paid, sender=recipient)


def test_buy_zero_reverts(surplus_cdp, recipient):
    with boa.reverts(dev="[cdp_erc20] amount must be greater than zero (0)."):
        surplus_cdp.buy_surplus(0, sender=recipient)


def test_buy_with_fee_on_transfer_pays_for_received(surplus_cdp, token, recipient):
    """A 1% transfer fee: the mUSD bought is priced on what arrives."""
    token.set_fee_bps(100)
    sent = _cost(500 * ETH)
    received = sent - sent // 100  # the token rounds its fee down

    bought = surplus_cdp.buy_surplus(sent, sender=recipient)

    assert surplus_cdp.reserve() == received
    assert bought == _bought(received)


def test_buy_when_transfer_fails_reverts(surplus_cdp, token, recipient):
    token.set_return_false(True)

    with boa.reverts(dev="[cdp_erc20] transfer failed"):
        surplus_cdp.buy_surplus(ETH // 10, sender=recipient)


def test_reserve_is_not_withdrawable_collateral(surplus_cdp, token, borrower, recipient):
    """The tokens the contract holds are exactly the positions plus the reserve."""
    surplus_cdp.buy_surplus(_cost(500 * ETH), sender=recipient)

    assert token.balanceOf(surplus_cdp.address) == held_collateral(
        surplus_cdp, [borrower, recipient]
    )


# ================= Bad debt =================


def test_surplus_absorbs_bad_debt(surplus_cdp, oracle, borrower, liquidator):
    oracle.set_answer(INSOLVENT_PRICE)
    surplus = surplus_cdp.surplus()

    surplus_cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    written_off = filter_logs(surplus_cdp, "Liquidate")[0].written_off
    settled = filter_logs(surplus_cdp, "Settle")[0].amount

    assert written_off > 0
    assert settled == written_off
    assert surplus_cdp.bad_debt() == 0
    assert surplus_cdp.surplus() == surplus - written_off


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


def test_cover_bad_debt_from_reserve(surplus_cdp, token, oracle, borrower, liquidator, recipient):
    """Money Flow: caller mUSD → burned against bad debt, reserve collateral → caller."""
    # Interest is sold for collateral, filling the reserve.
    surplus_cdp.buy_surplus(_cost(surplus_cdp.surplus()), sender=recipient)
    reserve = surplus_cdp.reserve()

    # Then a position goes insolvent with no surplus left to absorb it.
    oracle.set_answer(INSOLVENT_PRICE)
    surplus_cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    bad_debt = surplus_cdp.bad_debt()
    assert bad_debt > 0

    liquidator_tokens = token.balanceOf(liquidator)
    paid = surplus_cdp.cover_bad_debt(bad_debt, sender=liquidator)
    log = filter_logs(surplus_cdp, "CoverBadDebt")[0]

    # The 0.5% swap fee stays in the reserve.
    assert paid == bad_debt * (PRECISION - SWAP_FEE) // price_scaled(INSOLVENT_PRICE)
    assert (log.caller, log.amount, log.paid) == (liquidator, bad_debt, paid)
    assert surplus_cdp.bad_debt() == 0
    assert surplus_cdp.reserve() == reserve - paid
    assert token.balanceOf(liquidator) == liquidator_tokens + paid


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
    with boa.reverts(dev="[cdp_erc20] amount must be greater than zero (0)."):
        cdp.cover_bad_debt(0, sender=funded_liquidator)
