import boa

from tests.utils.constants import ETH, MAX_MINT_PER_ETH, MIN_COLLAT_RATIO, POSITION_DEBT
from tests.utils.helpers import filter_logs, to_feed_price


def test_mint_issues_debt_and_tokens(cdp, borrower):
    """Money Flow: new mUSD → borrower, debt recorded."""
    amount = 1000 * ETH
    cdp.deposit(value=ETH, sender=borrower)

    # ================= Execute =================
    cdp.mint(amount, sender=borrower)

    # ================= Verify state =================
    assert cdp.debt(borrower) == amount
    assert cdp.balanceOf(borrower) == amount
    assert cdp.totalSupply() == amount


def test_mint_emits_events(cdp, borrower):
    amount = 1000 * ETH
    cdp.deposit(value=ETH, sender=borrower)

    cdp.mint(amount, sender=borrower)

    mint_logs = filter_logs(cdp, "Mint")
    assert len(mint_logs) == 1
    assert mint_logs[0].user == borrower
    assert mint_logs[0].amount == amount

    transfer_logs = filter_logs(cdp, "Transfer")
    assert len(transfer_logs) == 1
    assert transfer_logs[0].sender == boa.eval("empty(address)")
    assert transfer_logs[0].receiver == borrower
    assert transfer_logs[0].value == amount


def test_mint_up_to_limit(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)

    cdp.mint(MAX_MINT_PER_ETH, sender=borrower)

    assert cdp.debt(borrower) == MAX_MINT_PER_ETH
    assert cdp.collat_ratio(borrower) >= MIN_COLLAT_RATIO


def test_mint_one_wei_above_limit_reverts(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)

    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.mint(MAX_MINT_PER_ETH + 1, sender=borrower)


def test_mint_in_steps_hits_same_limit(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)
    cdp.mint(MAX_MINT_PER_ETH // 2, sender=borrower)
    cdp.mint(MAX_MINT_PER_ETH - MAX_MINT_PER_ETH // 2, sender=borrower)

    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.mint(1, sender=borrower)


def test_mint_without_collateral_reverts(cdp, borrower):
    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.mint(1, sender=borrower)


def test_mint_limit_tracks_price(cdp, oracle, borrower):
    cdp.deposit(value=ETH, sender=borrower)
    cdp.mint(MAX_MINT_PER_ETH, sender=borrower)

    oracle.set_answer(to_feed_price(4000))

    cdp.mint(MAX_MINT_PER_ETH, sender=borrower)
    assert cdp.debt(borrower) == 2 * MAX_MINT_PER_ETH


def test_mint_does_not_change_collateral(cdp, borrower):
    cdp.deposit(value=ETH, sender=borrower)

    cdp.mint(1000 * ETH, sender=borrower)

    assert cdp.collateral(borrower) == ETH
    assert boa.env.get_balance(cdp.address) == ETH


def test_transferring_musd_does_not_move_debt(cdp, borrower_position, recipient):
    cdp.transfer(recipient, POSITION_DEBT, sender=borrower_position)

    assert cdp.debt(borrower_position) == POSITION_DEBT
    assert cdp.debt(recipient) == 0
