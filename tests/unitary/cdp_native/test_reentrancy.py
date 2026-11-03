"""Every function that pays out ETH does so with `raw_call` to the caller,
after its accounting. A caller contract that re-enters from its `__default__`
must hit the reentrancy lock.

The re-entered call is `mint(0)`: for a debt-free caller it succeeds on its
own (checked below), so the only thing that can make it revert mid-payout is
the lock, not some unrelated check."""

import boa

from tests.mocks.deployers import MOCK_REENTRANT_CALLER
from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    MAX_STABILITY_FEE,
    MAX_UINT256,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    PRECISION,
    YEAR,
)
from tests.utils.helpers import deploy_cdp_native, to_feed_price

# The default position is at 140% here: partially liquidatable.
PARTIAL_PRICE = to_feed_price(1400)
# And at 90% here: insolvent, so liquidating it writes off bad debt.
INSOLVENT_PRICE = to_feed_price(900)


def _attacker(cdp):
    return MOCK_REENTRANT_CALLER.deploy(cdp.address)


def _assert_reentry_blocked(cdp, attacker, calldata):
    """`calldata` succeeds while the attacker accepts ETH quietly, and reverts
    once it re-enters on receipt. Returns the state to the starting point."""
    with boa.env.anchor():
        attacker.forward(calldata)

    attacker.set_reenter_data(cdp.mint.prepare_calldata(0))
    with boa.reverts():
        attacker.forward(calldata)
    attacker.set_reenter_data(b"")


def test_reentry_payload_succeeds_on_its_own(cdp):
    attacker = _attacker(cdp)

    attacker.forward(cdp.mint.prepare_calldata(0))

    assert cdp.debt(attacker.address) == 0


def test_withdraw_reentry_reverts(cdp):
    attacker = _attacker(cdp)
    attacker.forward(cdp.deposit.prepare_calldata(), value=2 * ETH)

    _assert_reentry_blocked(cdp, attacker, cdp.withdraw.prepare_calldata(ETH))

    assert cdp.collateral(attacker.address) == 2 * ETH
    assert boa.env.get_balance(cdp.address) == 2 * ETH


def test_liquidate_reentry_reverts(cdp, oracle, borrower_position, funded_liquidator):
    attacker = _attacker(cdp)
    cdp.transfer(attacker.address, POSITION_DEBT, sender=funded_liquidator)
    oracle.set_answer(PARTIAL_PRICE)

    _assert_reentry_blocked(
        cdp, attacker, cdp.liquidate.prepare_calldata(borrower_position, MAX_UINT256)
    )

    assert cdp.debt(borrower_position) == POSITION_DEBT
    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL
    assert cdp.balanceOf(attacker.address) == POSITION_DEBT


def test_insolvent_liquidate_reentry_reverts(
    cdp, oracle, borrower_position, funded_liquidator
):
    """The write-off branch pays out all of the collateral; it is locked too."""
    attacker = _attacker(cdp)
    cdp.transfer(attacker.address, POSITION_DEBT, sender=funded_liquidator)
    oracle.set_answer(INSOLVENT_PRICE)

    _assert_reentry_blocked(
        cdp, attacker, cdp.liquidate.prepare_calldata(borrower_position, MAX_UINT256)
    )

    assert cdp.bad_debt() == 0
    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL


def test_redeem_reentry_reverts(cdp, borrower_position, funded_liquidator):
    attacker = _attacker(cdp)
    cdp.transfer(attacker.address, 100 * ETH, sender=funded_liquidator)

    _assert_reentry_blocked(
        cdp, attacker, cdp.redeem.prepare_calldata(borrower_position, 100 * ETH, 0)
    )

    assert cdp.debt(borrower_position) == POSITION_DEBT
    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL


def test_cover_bad_debt_reentry_reverts(oracle, borrower, liquidator, recipient):
    # A year of interest, sold for ETH, fills the reserve; then a position
    # goes insolvent with no surplus left to absorb it.
    oracle.set_answer(ETH_USD_PRICE)
    cdp = deploy_cdp_native(oracle.address, fee=MAX_STABILITY_FEE)
    cdp.deposit(value=20 * ETH, sender=recipient)
    cdp.mint(10_000 * ETH, sender=recipient)
    cdp.transfer(liquidator, 2_000 * ETH, sender=recipient)
    cdp.deposit(value=POSITION_COLLATERAL, sender=borrower)
    cdp.mint(POSITION_DEBT, sender=borrower)

    boa.env.time_travel(seconds=YEAR)
    oracle.set_answer(ETH_USD_PRICE)
    cdp.mint(0, sender=recipient)
    cdp.buy_surplus(
        value=cdp.surplus() * PRECISION // (ETH_USD_PRICE * 10**10), sender=recipient
    )
    oracle.set_answer(INSOLVENT_PRICE)
    cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    bad_debt = cdp.bad_debt()
    reserve = cdp.reserve()
    assert bad_debt > 0

    attacker = _attacker(cdp)
    cdp.transfer(attacker.address, bad_debt, sender=liquidator)

    _assert_reentry_blocked(cdp, attacker, cdp.cover_bad_debt.prepare_calldata(bad_debt))

    assert cdp.bad_debt() == bad_debt
    assert cdp.reserve() == reserve

