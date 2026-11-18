import boa

from tests.utils.constants import ETH
from tests.utils.helpers import filter_logs


def test_deposit_locks_collateral(cdp, borrower):
    """Money Flow: borrower ETH → cdp."""
    # ================= Capture initial state =================
    borrower_eth = boa.env.get_balance(borrower)

    # ================= Execute =================
    cdp.deposit(value=ETH, sender=borrower)

    # ================= Verify state and money flows =================
    assert cdp.collateral(borrower) == ETH
    assert cdp.debt(borrower) == 0
    assert boa.env.get_balance(cdp.address) == ETH
    assert boa.env.get_balance(borrower) == borrower_eth - ETH


def test_deposit_emits_event(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)

    logs = filter_logs(cdp, "Deposit")
    assert len(logs) == 1
    assert logs[0].user == borrower
    assert logs[0].amount == ETH


def test_deposit_accumulates(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)
    cdp.deposit(value=2 * ETH, sender=borrower)

    assert cdp.collateral(borrower) == 3 * ETH
    assert boa.env.get_balance(cdp.address) == 3 * ETH


def test_deposit_is_per_account(cdp, borrower, liquidator):
    cdp.deposit(value=ETH, sender=borrower)
    cdp.deposit(value=2 * ETH, sender=liquidator)

    assert cdp.collateral(borrower) == ETH
    assert cdp.collateral(liquidator) == 2 * ETH


def test_zero_deposit_reverts(cdp, borrower):
    with boa.reverts(dev="[cdp_native] msg.value must be greater than zero (0)."):
        cdp.deposit(sender=borrower)
