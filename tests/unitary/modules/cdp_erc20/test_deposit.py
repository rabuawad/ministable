import boa

from tests.mocks.deployers import MOCK_TOKEN_NO_RETURN
from tests.utils.constants import ETH, MAX_UINT256
from tests.utils.helpers import deploy_cdp_erc20, filter_logs


def test_deposit_pulls_collateral(cdp, token, funded_borrower):
    """Money Flow: borrower tokens → cdp."""
    borrower = funded_borrower
    # ================= Capture initial state =================
    borrower_tokens = token.balanceOf(borrower)

    # ================= Execute =================
    credited = cdp.deposit(ETH, sender=borrower)

    # ================= Verify state and money flows =================
    assert credited == ETH
    assert cdp.collateral(borrower) == ETH
    assert cdp.debt(borrower) == 0
    assert token.balanceOf(cdp.address) == ETH
    assert token.balanceOf(borrower) == borrower_tokens - ETH


def test_deposit_emits_event(cdp, funded_borrower):
    cdp.deposit(ETH, sender=funded_borrower)

    logs = filter_logs(cdp, "Deposit")
    assert len(logs) == 1
    assert logs[0].user == funded_borrower
    assert logs[0].amount == ETH


def test_deposit_accumulates(cdp, token, funded_borrower):
    cdp.deposit(ETH, sender=funded_borrower)
    cdp.deposit(2 * ETH, sender=funded_borrower)

    assert cdp.collateral(funded_borrower) == 3 * ETH
    assert token.balanceOf(cdp.address) == 3 * ETH


def test_deposit_does_not_mint(cdp, funded_borrower):
    cdp.deposit(ETH, sender=funded_borrower)

    assert cdp.totalSupply() == 0
    assert cdp.balanceOf(funded_borrower) == 0


def test_zero_deposit_reverts(cdp, funded_borrower):
    with boa.reverts(dev="[cdp_erc20] amount must be greater than zero (0)."):
        cdp.deposit(0, sender=funded_borrower)


def test_deposit_without_approval_reverts(cdp, token, borrower):
    token.mint(borrower, ETH)

    with boa.reverts():
        cdp.deposit(ETH, sender=borrower)


def test_deposit_more_than_balance_reverts(cdp, token, funded_borrower):
    with boa.reverts():
        cdp.deposit(token.balanceOf(funded_borrower) + 1, sender=funded_borrower)


def test_deposit_ignores_price(cdp, oracle, funded_borrower):
    """Deposits never read the oracle, so they work with a broken feed."""
    oracle.set_answer(0)

    cdp.deposit(ETH, sender=funded_borrower)

    assert cdp.collateral(funded_borrower) == ETH


def test_deposit_credits_only_own_position(cdp, funded_borrower, recipient):
    cdp.deposit(ETH, sender=funded_borrower)

    assert cdp.collateral(recipient) == 0


# ================= Awkward tokens =================


def test_fee_on_transfer_credits_amount_received(cdp, token, funded_borrower):
    """A 1% transfer fee: 1 token sent, 0.99 arrives and is credited."""
    token.set_fee_bps(100)

    credited = cdp.deposit(ETH, sender=funded_borrower)
    log = filter_logs(cdp, "Deposit")[0]

    assert credited == ETH * 99 // 100
    assert log.amount == credited
    assert cdp.collateral(funded_borrower) == credited
    assert token.balanceOf(cdp.address) == credited


def test_deposit_that_delivers_nothing_reverts(cdp, token, funded_borrower):
    token.set_fee_bps(10_000)

    with boa.reverts(dev="[cdp] zero deposit"):
        cdp.deposit(ETH, sender=funded_borrower)


def test_transfer_returning_false_reverts(cdp, token, funded_borrower):
    token.set_return_false(True)

    with boa.reverts(dev="[cdp_erc20] transfer failed"):
        cdp.deposit(ETH, sender=funded_borrower)


def test_token_without_return_value(oracle, borrower):
    """USDT-style tokens return no data from `transfer`/`transferFrom`."""
    token = MOCK_TOKEN_NO_RETURN.deploy(18)
    cdp = deploy_cdp_erc20(token.address, oracle.address)
    token.mint(borrower, 2 * ETH)
    token.approve(cdp.address, MAX_UINT256, sender=borrower)

    cdp.deposit(2 * ETH, sender=borrower)
    assert cdp.collateral(borrower) == 2 * ETH
    assert token.balanceOf(cdp.address) == 2 * ETH

    cdp.mint(1000 * ETH, sender=borrower)
    cdp.burn(1000 * ETH, sender=borrower)
    cdp.withdraw(2 * ETH, sender=borrower)
    assert token.balanceOf(borrower) == 2 * ETH
    assert token.balanceOf(cdp.address) == 0


def test_direct_transfer_is_not_a_deposit(cdp, token, funded_borrower):
    """Tokens sent with a plain `transfer` are not credited to anyone."""
    token.transfer(cdp.address, ETH, sender=funded_borrower)

    assert cdp.collateral(funded_borrower) == 0
    # The donation does not leak into later deposits either.
    assert cdp.deposit(ETH, sender=funded_borrower) == ETH
