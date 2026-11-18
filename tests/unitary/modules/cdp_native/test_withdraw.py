import boa

from tests.utils.constants import ETH, ORACLE_TIMEOUT, POSITION_DEBT
from tests.utils.helpers import filter_logs


def test_withdraw_without_debt(cdp, borrower):
    """Money Flow: cdp ETH → borrower."""
    cdp.deposit(value=ETH, sender=borrower)
    borrower_eth = boa.env.get_balance(borrower)

    cdp.withdraw(ETH, sender=borrower)

    assert cdp.collateral(borrower) == 0
    assert boa.env.get_balance(cdp.address) == 0
    assert boa.env.get_balance(borrower) == borrower_eth + ETH


def test_withdraw_emits_event(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)

    cdp.withdraw(ETH, sender=borrower)

    logs = filter_logs(cdp, "Withdraw")
    assert len(logs) == 1
    assert logs[0].user == borrower
    assert logs[0].amount == ETH


def test_withdraw_keeping_ratio(cdp, borrower):
    cdp.deposit(value=2 * ETH, sender=borrower)
    cdp.mint(POSITION_DEBT, sender=borrower)

    cdp.withdraw(ETH, sender=borrower)

    assert cdp.collateral(borrower) == ETH
    assert cdp.collat_ratio(borrower) == 2 * 10**18


def test_withdraw_down_to_limit(cdp, borrower_position):
    """1000 mUSD at $2000 needs exactly 0.75 ETH."""
    borrower = borrower_position

    cdp.withdraw(ETH // 4, sender=borrower)

    assert cdp.collateral(borrower) == 3 * ETH // 4
    assert cdp.collat_ratio(borrower) == 15 * 10**17


def test_withdraw_one_wei_past_limit_reverts(cdp, borrower_position):
    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.withdraw(ETH // 4 + 1, sender=borrower_position)


def test_withdraw_breaking_ratio_reverts(cdp, borrower_position):
    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.withdraw(ETH // 2, sender=borrower_position)


def test_withdraw_more_than_collateral_reverts(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)

    with boa.reverts():
        cdp.withdraw(ETH + 1, sender=borrower)


def test_withdraw_other_users_collateral_reverts(cdp, borrower, liquidator):
    cdp.deposit(value=ETH, sender=borrower)

    with boa.reverts():
        cdp.withdraw(ETH, sender=liquidator)


def test_withdraw_without_debt_ignores_oracle(cdp, oracle, borrower):
    """Debt-free positions never read the price, so a dead feed can't lock funds."""
    cdp.deposit(value=ETH, sender=borrower)
    oracle.set_answer(0)
    boa.env.time_travel(seconds=ORACLE_TIMEOUT + 1)

    cdp.withdraw(ETH, sender=borrower)

    assert cdp.collateral(borrower) == 0


def test_withdraw_to_rejecting_contract_reverts(cdp, receiver):
    receiver.deposit(value=ETH)
    receiver.set_accept_eth(False)

    with boa.reverts():
        receiver.withdraw(ETH)

    assert cdp.collateral(receiver.address) == ETH


def test_withdraw_reentrancy_reverts(cdp, receiver):
    """`__default__` of the receiver calls `withdraw` again while ETH is in flight."""
    receiver.deposit(value=2 * ETH)
    receiver.set_reenter(True)

    with boa.reverts():
        receiver.withdraw(ETH)

    assert cdp.collateral(receiver.address) == 2 * ETH
    assert boa.env.get_balance(cdp.address) == 2 * ETH


def test_withdraw_to_contract(cdp, receiver):
    receiver_eth = boa.env.get_balance(receiver.address)
    receiver.deposit(value=ETH)

    receiver.withdraw(ETH)

    assert cdp.collateral(receiver.address) == 0
    assert boa.env.get_balance(receiver.address) == receiver_eth + ETH
