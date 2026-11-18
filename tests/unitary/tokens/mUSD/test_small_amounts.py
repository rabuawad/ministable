"""Smallest-unit money flows through the deployed mUSD contract."""

import boa
import pytest
from eth_account import Account

from tests.utils.constants import MAX_STABILITY_FEE, MAX_UINT256
from tests.utils.helpers import deploy_stable, max_mintable, to_feed_price
from tests.utils.permit import sign_permit


# ================= Positions and token balances =================


@pytest.mark.parametrize("amount", [1, 2, 3])
def test_small_position_closes_exactly(stable, borrower, amount):
    initial = boa.env.get_balance(borrower)
    stable.deposit(value=amount, sender=borrower)
    stable.mint(amount, sender=borrower)
    assert stable.collateral(borrower) == amount
    assert stable.debt(borrower) == stable.balanceOf(borrower) == amount
    assert stable.total_debt_shares() == stable.totalSupply() == amount

    stable.burn(amount, sender=borrower)
    stable.withdraw(amount, sender=borrower)

    assert stable.debt(borrower) == stable.debt_shares(borrower) == 0
    assert stable.collat_ratio(borrower) == MAX_UINT256
    assert stable.totalSupply() == stable.total_debt_shares() == 0
    assert stable.balanceOf(borrower) == stable.collateral(borrower) == 0
    assert boa.env.get_balance(stable.address) == 0
    assert boa.env.get_balance(borrower) == initial


def test_one_wei_collateral_enforces_mint_and_withdraw_limits(stable, oracle, borrower):
    stable.deposit(value=1, sender=borrower)
    limit = max_mintable(1, oracle.answer())
    stable.mint(limit, sender=borrower)

    with boa.reverts(dev="[cdp] undercollateralized"):
        stable.mint(1, sender=borrower)
    with boa.reverts(dev="[cdp] undercollateralized"):
        stable.withdraw(1, sender=borrower)

    assert stable.total_debt_shares() == stable.debt(borrower) == limit
    assert stable.totalSupply() == stable.balanceOf(borrower) == limit
    assert stable.collateral(borrower) == boa.env.get_balance(stable.address) == 1


def test_one_wei_adjustments_leave_other_position_intact(stable, borrower, recipient):
    stable.deposit(value=1, sender=recipient)
    stable.mint(1, sender=recipient)
    stable.deposit(value=2, sender=borrower)
    stable.mint(2, sender=borrower)

    stable.burn(1, sender=borrower)
    stable.withdraw(1, sender=borrower)

    for owner in (borrower, recipient):
        assert stable.debt(owner) == stable.debt_shares(owner) == 1
        assert stable.collateral(owner) == stable.balanceOf(owner) == 1
    assert stable.totalSupply() == stable.total_debt_shares() == 2
    assert boa.env.get_balance(stable.address) == 2


def test_partial_burn_must_retire_a_share_after_interest_accrues(oracle, borrower):
    stable = deploy_stable(oracle.address, fee=MAX_STABILITY_FEE)
    stable.deposit(value=1, sender=borrower)
    stable.mint(2, sender=borrower)
    boa.env.time_travel(seconds=1)

    assert stable.debt(borrower) == 3
    with boa.reverts(dev="[cdp] repayment below one debt share"):
        stable.burn(1, sender=borrower)

    stable.burn(0, sender=borrower)
    assert stable.balanceOf(borrower) == stable.totalSupply() == 2
    assert stable.debt_shares(borrower) == stable.total_debt_shares() == 2
    assert stable.debt(borrower) == 3
    assert stable.collateral(borrower) == boa.env.get_balance(stable.address) == 1
    assert stable.surplus() == 0

    # Two base units is the smallest partial payment that removes one share.
    stable.burn(2, sender=borrower)
    assert stable.balanceOf(borrower) == stable.totalSupply() == 0
    assert stable.debt_shares(borrower) == stable.total_debt_shares() == 1
    assert stable.debt(borrower) == 2


@pytest.mark.parametrize("action, price_cents", [("redeem", 50), ("liquidate", 45)])
def test_third_party_repayment_below_one_share_reverts(oracle, borrower, recipient, action, price_cents):
    stable = deploy_stable(oracle.address, fee=MAX_STABILITY_FEE)
    stable.deposit(value=12, sender=borrower)
    stable.mint(3, sender=borrower)
    stable.transfer(recipient, 1, sender=borrower)
    boa.env.time_travel(seconds=1)
    # The rounded debt is four. The two prices give ratios of 150% and 125%.
    oracle.set_answer(to_feed_price(price_cents) // 100)
    recipient_eth = boa.env.get_balance(recipient)

    with boa.reverts(dev="[cdp] repayment below one debt share"):
        if action == "redeem":
            stable.redeem(borrower, 1, 1, sender=recipient)
        else:
            stable.liquidate(borrower, 1, sender=recipient)

    assert stable.debt(borrower) == 4
    assert stable.debt_shares(borrower) == stable.total_debt_shares() == 3
    assert stable.collateral(borrower) == boa.env.get_balance(stable.address) == 12
    assert stable.balanceOf(recipient) == 1
    assert stable.totalSupply() == 3
    assert boa.env.get_balance(recipient) == recipient_eth


def test_full_repayment_of_rounded_debt_clears_last_share(oracle, borrower, recipient):
    stable = deploy_stable(oracle.address, fee=MAX_STABILITY_FEE)
    stable.deposit(value=1, sender=recipient)
    stable.mint(1, sender=recipient)
    boa.env.time_travel(seconds=1)

    stable.deposit(value=1, sender=borrower)
    stable.mint(1, sender=borrower)
    assert stable.balanceOf(borrower) == stable.debt_shares(borrower) == 1
    assert stable.debt(borrower) == 2

    stable.transfer(borrower, 1, sender=recipient)
    stable.burn(2, sender=borrower)
    stable.withdraw(1, sender=borrower)
    assert stable.debt(borrower) == stable.collateral(borrower) == 0
    assert stable.debt_shares(borrower) == stable.totalSupply() == 0
    assert stable.total_debt_shares() == stable.debt_shares(recipient) == 1


@pytest.mark.parametrize("authorization", ["approve", "permit"])
def test_one_wei_allowance_is_consumed_once(stable, borrower, recipient, authorization):
    holder = Account.create()
    stable.deposit(value=1, sender=borrower)
    stable.mint(1, sender=borrower)
    assert stable.transfer(holder.address, 1, sender=borrower)

    if authorization == "permit":
        deadline = boa.env.timestamp + 60
        signature = sign_permit(stable, holder, recipient, 1, deadline)
        stable.permit(holder.address, recipient, 1, deadline, *signature, sender=recipient)
        assert stable.nonces(holder.address) == 1
    else:
        assert stable.approve(recipient, 1, sender=holder.address)
    assert stable.allowance(holder.address, recipient) == 1

    assert stable.transferFrom(holder.address, recipient, 1, sender=recipient)
    with boa.reverts(dev="[erc20] insufficient allowance"):
        stable.transferFrom(holder.address, recipient, 1, sender=recipient)
    assert stable.allowance(holder.address, recipient) == 0
    assert stable.balanceOf(holder.address) == stable.balanceOf(borrower) == 0
    assert stable.balanceOf(recipient) == stable.totalSupply() == 1
    assert stable.debt(borrower) == 1
    assert stable.debt(recipient) == stable.debt(holder.address) == 0


# ================= Redemption and liquidation =================


def test_one_wei_redemption_checks_minimum_payout(stable, oracle, borrower, recipient):
    # At $0.50, one mUSD base unit buys one native wei after fees.
    oracle.set_answer(to_feed_price(1) // 2)
    stable.deposit(value=4, sender=borrower)
    stable.mint(1, sender=borrower)
    stable.transfer(recipient, 1, sender=borrower)
    initial = boa.env.get_balance(recipient)

    with boa.reverts(dev="[cdp] slippage"):
        stable.redeem(borrower, 1, 2, sender=recipient)
    with boa.reverts(dev="[cdp_native] min paid amount must be greater than zero (0)."):
        stable.redeem(borrower, 1, sender=recipient)

    assert stable.redeem(borrower, 1, 1, sender=recipient) == 1
    assert boa.env.get_balance(recipient) == initial + 1
    assert stable.collateral(borrower) == boa.env.get_balance(stable.address) == 3
    assert stable.debt(borrower) == stable.total_debt_shares() == 0
    assert stable.balanceOf(recipient) == stable.totalSupply() == 0


def test_one_wei_redemption_with_zero_quote_reverts(stable, borrower):
    stable.deposit(value=1, sender=borrower)
    stable.mint(1, sender=borrower)
    with boa.reverts(dev="[cdp] slippage"):
        stable.redeem(borrower, 1, 1, sender=borrower)
    assert stable.collateral(borrower) == stable.debt(borrower) == 1
    assert stable.balanceOf(borrower) == stable.totalSupply() == 1


@pytest.mark.parametrize(
    "collateral, debt, price, seized, remaining_debt, bad_debt",
    [
        pytest.param(6, 5, 1, 1, 4, 0, id="partial"),
        pytest.param(1, 1000, 1400, 0, 999, 0, id="partial-zero-payout"),
        pytest.param(1, 1, 1, 1, 0, 0, id="fully-covered"),
        pytest.param(2, 3, 1, 2, 0, 2, id="write-off"),
    ],
)
def test_liquidation_capped_at_one_wei(
    stable, oracle, borrower, liquidator, collateral, debt, price, seized, remaining_debt, bad_debt
):
    stable.deposit(value=collateral, sender=borrower)
    stable.mint(debt, sender=borrower)
    stable.transfer(liquidator, 1, sender=borrower)
    oracle.set_answer(to_feed_price(price))
    initial = boa.env.get_balance(liquidator)

    assert stable.liquidate(borrower, 1, sender=liquidator) == 1

    assert boa.env.get_balance(liquidator) == initial + seized
    assert stable.collateral(borrower) == boa.env.get_balance(stable.address) == collateral - seized
    assert stable.debt(borrower) == stable.total_debt_shares() == remaining_debt
    assert stable.bad_debt() == bad_debt
    assert stable.balanceOf(liquidator) == 0
    assert stable.totalSupply() == stable.balanceOf(borrower) == remaining_debt + bad_debt


@pytest.mark.parametrize("debt", [3, 4], ids=["fully-covered", "insolvent"])
def test_one_wei_cap_below_required_closeout_reverts(stable, oracle, borrower, liquidator, debt):
    stable.deposit(value=3, sender=borrower)
    stable.mint(debt, sender=borrower)
    stable.transfer(liquidator, 1, sender=borrower)
    oracle.set_answer(to_feed_price(1))

    with boa.reverts(dev="[cdp] repay too small"):
        stable.liquidate(borrower, 1, sender=liquidator)

    assert stable.collateral(borrower) == boa.env.get_balance(stable.address) == 3
    assert stable.totalSupply() == stable.debt(borrower) == debt
    assert stable.balanceOf(liquidator) == 1
    assert stable.bad_debt() == 0


# ================= Surplus and reserve =================


def test_one_wei_surplus_purchase_checks_quote(stable, oracle, borrower, recipient):
    stable.deposit(value=2, sender=borrower)
    stable.mint(1, sender=borrower)
    stable.transfer(stable.address, 1, sender=borrower)
    initial = boa.env.get_balance(recipient)

    with boa.reverts(dev="[cdp] not enough surplus"):
        stable.buy_surplus(value=1, sender=recipient)
    oracle.set_answer(to_feed_price(1))
    with boa.reverts(dev="[cdp] zero purchase"):
        stable.buy_surplus(value=1, sender=recipient)

    # At $2, one native wei buys one mUSD base unit after the spread.
    oracle.set_answer(to_feed_price(2))
    assert stable.buy_surplus(value=1, sender=recipient) == 1
    assert stable.balanceOf(recipient) == stable.totalSupply() == 1
    assert stable.surplus() == 0
    assert stable.reserve() == 1
    assert boa.env.get_balance(stable.address) == stable.collateral(borrower) + 1
    assert boa.env.get_balance(recipient) == initial - 1


@pytest.mark.parametrize("price_cents, paid", [(75, 1), (200, 0)])
def test_cover_one_wei_of_bad_debt(stable, oracle, borrower, liquidator, price_cents, paid):
    oracle.set_answer(to_feed_price(2))
    stable.deposit(value=4, sender=borrower)
    stable.mint(5, sender=borrower)
    stable.transfer(stable.address, 1, sender=borrower)
    stable.buy_surplus(value=1, sender=liquidator)
    stable.transfer(liquidator, 2, sender=borrower)

    oracle.set_answer(to_feed_price(3) // 4)
    assert stable.liquidate(borrower, 2, sender=liquidator) == 2
    assert stable.bad_debt() == stable.totalSupply() == 3
    assert stable.reserve() == stable.balanceOf(liquidator) == 1

    oracle.set_answer(to_feed_price(price_cents) // 100)
    initial = boa.env.get_balance(liquidator)
    assert stable.cover_bad_debt(1, sender=liquidator) == paid

    assert stable.bad_debt() == stable.totalSupply() == 2
    assert stable.reserve() == boa.env.get_balance(stable.address) == 1 - paid
    assert stable.balanceOf(liquidator) == 0
    assert boa.env.get_balance(liquidator) == initial + paid
