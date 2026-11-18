import boa

from tests.utils.constants import ETH, POSITION_DEBT
from tests.utils.helpers import filter_logs


def test_burn_repays_debt(cdp, borrower_position):
    """Money Flow: borrower mUSD → burned, debt reduced."""
    borrower = borrower_position
    amount = 400 * ETH

    cdp.burn(amount, sender=borrower)

    assert cdp.debt(borrower) == POSITION_DEBT - amount
    assert cdp.balanceOf(borrower) == POSITION_DEBT - amount
    assert cdp.totalSupply() == POSITION_DEBT - amount


def test_burn_emits_events(cdp, borrower_position):
    borrower = borrower_position
    amount = 400 * ETH

    cdp.burn(amount, sender=borrower)

    burn_logs = filter_logs(cdp, "Burn")
    assert len(burn_logs) == 1
    assert burn_logs[0].user == borrower
    assert burn_logs[0].amount == amount

    transfer_logs = filter_logs(cdp, "Transfer")
    assert len(transfer_logs) == 1
    assert transfer_logs[0].sender == borrower
    assert transfer_logs[0].receiver == boa.eval("empty(address)")
    assert transfer_logs[0].value == amount


def test_burn_full_debt_restores_max_ratio(cdp, borrower_position):
    borrower = borrower_position

    cdp.burn(POSITION_DEBT, sender=borrower)

    assert cdp.debt(borrower) == 0
    assert cdp.collat_ratio(borrower) == 2**256 - 1


def test_burn_does_not_release_collateral(cdp, borrower_position):
    borrower = borrower_position

    cdp.burn(POSITION_DEBT, sender=borrower)

    assert cdp.collateral(borrower) == ETH
    assert boa.env.get_balance(cdp.address) == ETH


def test_burn_more_than_debt_reverts(cdp, borrower_position):
    with boa.reverts():
        cdp.burn(POSITION_DEBT + 1, sender=borrower_position)


def test_burn_without_tokens_reverts(cdp, borrower_position, recipient):
    """Debt cannot be repaid once the mUSD has been transferred away."""
    borrower = borrower_position
    cdp.transfer(recipient, POSITION_DEBT, sender=borrower)

    with boa.reverts(dev="[erc20] burn amount exceeds balance"):
        cdp.burn(1, sender=borrower)


def test_burn_without_debt_reverts(cdp, borrower_position, recipient):
    """Holding mUSD does not let a non-borrower burn it."""
    cdp.transfer(recipient, ETH, sender=borrower_position)

    with boa.reverts():
        cdp.burn(ETH, sender=recipient)
