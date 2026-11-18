import boa

from tests.utils.constants import ETH, ETH_USD_PRICE, POSITION_COLLATERAL, POSITION_DEBT
from tests.utils.helpers import filter_logs, max_mintable

# 1000 mUSD at $2000 needs 0.75 tokens at 150%.
FREE_COLLATERAL = POSITION_COLLATERAL - 3 * ETH // 4


def test_withdraw_returns_collateral(cdp, token, funded_borrower):
    """Money Flow: cdp tokens → borrower."""
    borrower = funded_borrower
    borrower_tokens = token.balanceOf(borrower)
    cdp.deposit(2 * ETH, sender=borrower)

    cdp.withdraw(ETH, sender=borrower)

    assert cdp.collateral(borrower) == ETH
    assert token.balanceOf(cdp.address) == ETH
    assert token.balanceOf(borrower) == borrower_tokens - ETH


def test_withdraw_emits_event(cdp, funded_borrower):
    cdp.deposit(ETH, sender=funded_borrower)

    cdp.withdraw(ETH, sender=funded_borrower)
    logs = filter_logs(cdp, "Withdraw")

    assert len(logs) == 1
    assert (logs[0].user, logs[0].amount) == (funded_borrower, ETH)


def test_withdraw_free_collateral(cdp, borrower_position):
    cdp.withdraw(FREE_COLLATERAL, sender=borrower_position)

    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL - FREE_COLLATERAL


def test_withdraw_past_min_ratio_reverts(cdp, borrower_position):
    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.withdraw(FREE_COLLATERAL + 1, sender=borrower_position)


def test_withdraw_more_than_collateral_reverts(cdp, funded_borrower):
    cdp.deposit(ETH, sender=funded_borrower)

    with boa.reverts():
        cdp.withdraw(ETH + 1, sender=funded_borrower)


def test_withdraw_at_max_mint_reverts(cdp, funded_borrower):
    cdp.deposit(POSITION_COLLATERAL, sender=funded_borrower)
    cdp.mint(max_mintable(POSITION_COLLATERAL, ETH_USD_PRICE), sender=funded_borrower)

    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.withdraw(1, sender=funded_borrower)


def test_withdraw_cannot_touch_other_positions(cdp, borrower_position, recipient):
    with boa.reverts():
        cdp.withdraw(1, sender=recipient)


def test_debt_free_withdraw_ignores_price(cdp, oracle, funded_borrower):
    """Without debt the ratio is never priced, so exits work with a broken feed."""
    cdp.deposit(ETH, sender=funded_borrower)
    oracle.set_answer(0)

    cdp.withdraw(ETH, sender=funded_borrower)

    assert cdp.collateral(funded_borrower) == 0


def test_withdraw_with_debt_needs_price(cdp, oracle, borrower_position):
    oracle.set_answer(0)

    with boa.reverts(dev="[cdp] invalid price"):
        cdp.withdraw(1, sender=borrower_position)


def test_close_position(cdp, token, borrower_position):
    """Repay and withdraw everything: the borrower ends with what they started."""
    borrower_tokens = token.balanceOf(borrower_position) + POSITION_COLLATERAL

    cdp.burn(POSITION_DEBT, sender=borrower_position)
    cdp.withdraw(POSITION_COLLATERAL, sender=borrower_position)

    assert cdp.collateral(borrower_position) == 0
    assert cdp.debt(borrower_position) == 0
    assert token.balanceOf(borrower_position) == borrower_tokens
    assert token.balanceOf(cdp.address) == 0


# ================= Awkward tokens =================


def test_transfer_returning_false_reverts(cdp, token, funded_borrower):
    cdp.deposit(ETH, sender=funded_borrower)
    token.set_return_false(True)

    with boa.reverts(dev="[cdp_erc20] transfer failed"):
        cdp.withdraw(ETH, sender=funded_borrower)

    assert cdp.collateral(funded_borrower) == ETH


def test_token_callback_cannot_reenter(cdp, token, funded_borrower, recipient):
    """A token that calls back into the CDP mid-transfer hits the lock,
    even for a view: `surplus()` is fine on its own."""
    cdp.deposit(ETH, sender=funded_borrower)
    token.set_hook(cdp.address, cdp.surplus.prepare_calldata())

    # Outside the CDP the hook succeeds...
    token.transfer(recipient, 1, sender=funded_borrower)

    # ...but from inside `withdraw` it re-enters and reverts.
    with boa.reverts():
        cdp.withdraw(ETH, sender=funded_borrower)

    assert cdp.collateral(funded_borrower) == ETH
