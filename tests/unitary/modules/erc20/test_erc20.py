import boa

from .conftest import HOLDER_BALANCE
from tests.utils.constants import ETH, MAX_UINT256, ZERO_ADDRESS
from tests.utils.helpers import filter_logs

# ================= Transfer =================


def test_transfer(musd, holder, recipient):
    musd.transfer(recipient, 100 * ETH, sender=holder)

    assert musd.balanceOf(recipient) == 100 * ETH
    assert musd.balanceOf(holder) == HOLDER_BALANCE - 100 * ETH
    assert musd.totalSupply() == HOLDER_BALANCE


def test_transfer_emits_event(musd, holder, recipient):
    musd.transfer(recipient, 100 * ETH, sender=holder)

    logs = filter_logs(musd, "Transfer")
    assert len(logs) == 1
    assert logs[0].sender == holder
    assert logs[0].receiver == recipient
    assert logs[0].value == 100 * ETH


def test_transfer_whole_balance(musd, holder, recipient):
    musd.transfer(recipient, HOLDER_BALANCE, sender=holder)

    assert musd.balanceOf(holder) == 0
    assert musd.balanceOf(recipient) == HOLDER_BALANCE


def test_transfer_to_self(musd, holder):
    musd.transfer(holder, 100 * ETH, sender=holder)

    assert musd.balanceOf(holder) == HOLDER_BALANCE


def test_transfer_exceeding_balance_reverts(musd, holder, recipient):
    with boa.reverts(dev="[erc20] transfer amount exceeds balance"):
        musd.transfer(recipient, HOLDER_BALANCE + 1, sender=holder)


def test_transfer_to_zero_address_reverts(musd, holder):
    with boa.reverts(dev="[erc20] transfer to the zero address"):
        musd.transfer(ZERO_ADDRESS, 1, sender=holder)


# ================= Approve and transferFrom =================


def test_approve(musd, borrower, recipient):
    musd.approve(recipient, 100 * ETH, sender=borrower)

    # Read logs before any other call: `get_logs` reflects the last call only.
    logs = filter_logs(musd, "Approval")
    assert len(logs) == 1
    assert logs[0].owner == borrower
    assert logs[0].spender == recipient
    assert logs[0].value == 100 * ETH
    assert musd.allowance(borrower, recipient) == 100 * ETH


def test_approve_overwrites(musd, borrower, recipient):
    musd.approve(recipient, 100 * ETH, sender=borrower)
    musd.approve(recipient, 5 * ETH, sender=borrower)

    assert musd.allowance(borrower, recipient) == 5 * ETH


def test_approve_zero_address_reverts(musd, borrower):
    with boa.reverts(dev="[erc20] approve to the zero address"):
        musd.approve(ZERO_ADDRESS, 1, sender=borrower)


def test_transfer_from(musd, holder, recipient):
    musd.approve(recipient, 100 * ETH, sender=holder)

    musd.transferFrom(holder, recipient, 60 * ETH, sender=recipient)

    assert musd.balanceOf(recipient) == 60 * ETH
    assert musd.allowance(holder, recipient) == 40 * ETH


def test_transfer_from_infinite_allowance_not_spent(musd, holder, recipient):
    musd.approve(recipient, MAX_UINT256, sender=holder)

    musd.transferFrom(holder, recipient, 60 * ETH, sender=recipient)

    assert musd.allowance(holder, recipient) == MAX_UINT256


def test_transfer_from_exceeding_allowance_reverts(musd, holder, recipient):
    musd.approve(recipient, 10 * ETH, sender=holder)

    with boa.reverts(dev="[erc20] insufficient allowance"):
        musd.transferFrom(holder, recipient, 10 * ETH + 1, sender=recipient)


def test_transfer_from_exceeding_balance_reverts(musd, holder, recipient):
    musd.approve(recipient, MAX_UINT256, sender=holder)

    with boa.reverts(dev="[erc20] transfer amount exceeds balance"):
        musd.transferFrom(holder, recipient, HOLDER_BALANCE + 1, sender=recipient)


# ================= Internal mint and burn =================
# Exposed by the harness; in production only the CDP engine calls them.


def test_mint(musd, recipient):
    musd.mint(recipient, 100 * ETH)
    logs = filter_logs(musd, "Transfer")

    assert musd.balanceOf(recipient) == 100 * ETH
    assert musd.totalSupply() == 100 * ETH
    assert (logs[0].sender, logs[0].receiver, logs[0].value) == (
        ZERO_ADDRESS,
        recipient,
        100 * ETH,
    )


def test_mint_to_zero_address_reverts(musd):
    with boa.reverts(dev="[erc20] mint to the zero address"):
        musd.mint(ZERO_ADDRESS, 1)


def test_burn(musd, holder):
    musd.burn(holder, 100 * ETH)
    logs = filter_logs(musd, "Transfer")

    assert musd.balanceOf(holder) == HOLDER_BALANCE - 100 * ETH
    assert musd.totalSupply() == HOLDER_BALANCE - 100 * ETH
    assert (logs[0].sender, logs[0].receiver, logs[0].value) == (
        holder,
        ZERO_ADDRESS,
        100 * ETH,
    )


def test_burn_exceeding_balance_reverts(musd, holder):
    with boa.reverts(dev="[erc20] burn amount exceeds balance"):
        musd.burn(holder, HOLDER_BALANCE + 1)


def test_burn_from_zero_address_reverts(musd):
    with boa.reverts(dev="[erc20] burn from the zero address"):
        musd.burn(ZERO_ADDRESS, 0)
