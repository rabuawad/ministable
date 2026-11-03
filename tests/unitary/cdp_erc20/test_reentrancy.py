"""Every function that pays out collateral calls the token's `transfer` after
its accounting. A token that calls back into the CDP mid-transfer must hit
the reentrancy lock. `withdraw` is covered in `test_withdraw.py`.

The callback is the `surplus()` view, which succeeds on its own, so the only
thing that can make it revert mid-payout is the lock."""

import boa

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
from tests.utils.helpers import deploy_cdp_erc20, fund, to_feed_price

PARTIAL_PRICE = to_feed_price(1400)
INSOLVENT_PRICE = to_feed_price(900)


def _assert_reentry_blocked(cdp, token, call):
    """`call()` succeeds with a quiet token, and reverts once the token calls
    back into `cdp` on transfer. Returns the state to the starting point."""
    with boa.env.anchor():
        call()

    token.set_hook(cdp.address, cdp.surplus.prepare_calldata())
    with boa.reverts():
        call()
    token.set_hook("0x" + "00" * 20, b"")


def test_liquidate_reentry_reverts(cdp, token, oracle, borrower_position, funded_liquidator):
    oracle.set_answer(PARTIAL_PRICE)

    _assert_reentry_blocked(
        cdp,
        token,
        lambda: cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator),
    )

    assert cdp.debt(borrower_position) == POSITION_DEBT
    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL


def test_insolvent_liquidate_reentry_reverts(
    cdp, token, oracle, borrower_position, funded_liquidator
):
    oracle.set_answer(INSOLVENT_PRICE)

    _assert_reentry_blocked(
        cdp,
        token,
        lambda: cdp.liquidate(borrower_position, MAX_UINT256, sender=funded_liquidator),
    )

    assert cdp.bad_debt() == 0
    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL


def test_redeem_reentry_reverts(cdp, token, borrower_position, funded_liquidator):
    _assert_reentry_blocked(
        cdp,
        token,
        lambda: cdp.redeem(borrower_position, 100 * ETH, sender=funded_liquidator),
    )

    assert cdp.debt(borrower_position) == POSITION_DEBT
    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL


def test_cover_bad_debt_reentry_reverts(token, oracle, borrower, liquidator, recipient):
    # A year of interest, sold for collateral, fills the reserve; then a
    # position goes insolvent with no surplus left to absorb it.
    oracle.set_answer(ETH_USD_PRICE)
    cdp = deploy_cdp_erc20(token.address, oracle.address, fee=MAX_STABILITY_FEE)
    for account in (borrower, liquidator, recipient):
        fund(token, cdp, account)
    cdp.deposit(20 * ETH, sender=recipient)
    cdp.mint(10_000 * ETH, sender=recipient)
    cdp.transfer(liquidator, 2_000 * ETH, sender=recipient)
    cdp.deposit(POSITION_COLLATERAL, sender=borrower)
    cdp.mint(POSITION_DEBT, sender=borrower)

    boa.env.time_travel(seconds=YEAR)
    oracle.set_answer(ETH_USD_PRICE)
    cdp.mint(0, sender=recipient)
    cdp.buy_surplus(cdp.surplus() * PRECISION // (ETH_USD_PRICE * 10**10), sender=recipient)
    oracle.set_answer(INSOLVENT_PRICE)
    cdp.liquidate(borrower, MAX_UINT256, sender=liquidator)
    bad_debt = cdp.bad_debt()
    reserve = cdp.reserve()
    assert bad_debt > 0

    _assert_reentry_blocked(
        cdp, token, lambda: cdp.cover_bad_debt(bad_debt, sender=liquidator)
    )

    assert cdp.bad_debt() == bad_debt
    assert cdp.reserve() == reserve


def test_pulls_are_locked_too(cdp, token, funded_borrower):
    """`deposit` and `buy_surplus` pull the token in; a callback from that
    transfer is inside the lock as well."""
    _assert_reentry_blocked(cdp, token, lambda: cdp.deposit(ETH, sender=funded_borrower))
