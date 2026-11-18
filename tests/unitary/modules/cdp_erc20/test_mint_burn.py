import boa

from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    MIN_COLLAT_RATIO,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    PRECISION,
)
from tests.utils.helpers import filter_logs, max_mintable

MAX_MINT = max_mintable(POSITION_COLLATERAL, ETH_USD_PRICE)


# ================= Mint =================


def test_mint(cdp, funded_borrower):
    """Money Flow: collateral locked → mUSD minted to the borrower, owed as debt."""
    borrower = funded_borrower
    cdp.deposit(POSITION_COLLATERAL, sender=borrower)

    cdp.mint(POSITION_DEBT, sender=borrower)

    assert cdp.balanceOf(borrower) == POSITION_DEBT
    assert cdp.totalSupply() == POSITION_DEBT
    assert cdp.debt(borrower) == POSITION_DEBT
    assert cdp.debt_shares(borrower) == POSITION_DEBT
    assert cdp.total_debt_shares() == POSITION_DEBT
    assert cdp.collat_ratio(borrower) == 2 * PRECISION


def test_mint_emits_events(cdp, funded_borrower):
    cdp.deposit(POSITION_COLLATERAL, sender=funded_borrower)

    cdp.mint(POSITION_DEBT, sender=funded_borrower)
    logs = filter_logs(cdp, "Mint")
    transfers = filter_logs(cdp, "Transfer")

    assert len(logs) == 1
    assert (logs[0].user, logs[0].amount) == (funded_borrower, POSITION_DEBT)
    assert len(transfers) == 1
    assert transfers[0].receiver == funded_borrower
    assert transfers[0].value == POSITION_DEBT


def test_mint_up_to_min_ratio(cdp, funded_borrower):
    cdp.deposit(POSITION_COLLATERAL, sender=funded_borrower)

    cdp.mint(MAX_MINT, sender=funded_borrower)

    assert cdp.collat_ratio(funded_borrower) >= MIN_COLLAT_RATIO


def test_mint_past_min_ratio_reverts(cdp, funded_borrower):
    cdp.deposit(POSITION_COLLATERAL, sender=funded_borrower)

    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.mint(MAX_MINT + 1, sender=funded_borrower)


def test_mint_in_steps_hits_same_limit(cdp, funded_borrower):
    cdp.deposit(POSITION_COLLATERAL, sender=funded_borrower)
    cdp.mint(MAX_MINT // 2, sender=funded_borrower)
    cdp.mint(MAX_MINT - MAX_MINT // 2, sender=funded_borrower)

    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.mint(1, sender=funded_borrower)


def test_mint_without_collateral_reverts(cdp, funded_borrower):
    with boa.reverts(dev="[cdp] undercollateralized"):
        cdp.mint(1, sender=funded_borrower)


def test_mint_zero_is_noop(cdp, funded_borrower):
    cdp.mint(0, sender=funded_borrower)

    assert cdp.debt(funded_borrower) == 0
    assert cdp.totalSupply() == 0


def test_collat_ratio_of_debt_free_position_is_max(cdp, funded_borrower):
    cdp.deposit(ETH, sender=funded_borrower)

    assert cdp.collat_ratio(funded_borrower) == 2**256 - 1


# ================= Burn =================


def test_burn_repays_debt(cdp, borrower_position):
    """Money Flow: borrower mUSD → burned, debt cut by the same amount."""
    cdp.burn(400 * ETH, sender=borrower_position)

    assert cdp.debt(borrower_position) == POSITION_DEBT - 400 * ETH
    assert cdp.balanceOf(borrower_position) == POSITION_DEBT - 400 * ETH
    assert cdp.totalSupply() == POSITION_DEBT - 400 * ETH
    # Collateral is untouched until withdrawn.
    assert cdp.collateral(borrower_position) == POSITION_COLLATERAL


def test_burn_whole_debt_clears_shares(cdp, borrower_position):
    cdp.burn(POSITION_DEBT, sender=borrower_position)

    assert cdp.debt(borrower_position) == 0
    assert cdp.debt_shares(borrower_position) == 0
    assert cdp.total_debt_shares() == 0


def test_burn_emits_events(cdp, borrower_position):
    cdp.burn(POSITION_DEBT, sender=borrower_position)
    logs = filter_logs(cdp, "Burn")
    transfers = filter_logs(cdp, "Transfer")

    assert len(logs) == 1
    assert (logs[0].user, logs[0].amount) == (borrower_position, POSITION_DEBT)
    assert len(transfers) == 1
    assert transfers[0].sender == borrower_position
    assert transfers[0].value == POSITION_DEBT


def test_burn_more_than_debt_reverts(cdp, borrower_position, funded_liquidator):
    cdp.transfer(borrower_position, ETH, sender=funded_liquidator)

    with boa.reverts(dev="[cdp] repay exceeds debt"):
        cdp.burn(POSITION_DEBT + 1, sender=borrower_position)


def test_burn_without_musd_reverts(cdp, borrower_position, recipient):
    cdp.transfer(recipient, POSITION_DEBT, sender=borrower_position)

    with boa.reverts(dev="[erc20] burn amount exceeds balance"):
        cdp.burn(1, sender=borrower_position)


def test_burn_with_bought_musd(cdp, borrower_position, funded_liquidator):
    """mUSD is fungible: a borrower can repay with mUSD minted by someone else."""
    cdp.transfer(borrower_position, POSITION_DEBT, sender=funded_liquidator)

    cdp.burn(POSITION_DEBT, sender=borrower_position)

    assert cdp.debt(borrower_position) == 0
    assert cdp.balanceOf(borrower_position) == POSITION_DEBT
