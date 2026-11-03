"""The deployed contract, `src/ministable.vy`. The module tests run against
harnesses; these check what only the production wiring adds: plain transfers
as deposits, the constructor, and the exact external surface."""

import boa
import pytest
from eth.exceptions import Revert

from src import ministable
from tests.mocks.deployers import MOCK_AGGREGATOR, MOCK_REENTRANT_CALLER
from tests.utils.constants import (
    ETH,
    MAX_STABILITY_FEE,
    MAX_UINT256,
    MIN_COLLAT_RATIO,
    ORACLE_TIMEOUT,
    POSITION_COLLATERAL,
    POSITION_DEBT,
    VARIANT_NATIVE,
    ZERO_ADDRESS,
)
from tests.utils.helpers import deploy_stable, filter_logs, max_mintable, to_feed_price

# Every external function and getter of the deployed contract. A change here
# changes what users and integrators can call, so it should be deliberate.
EXPECTED_FUNCTIONS = {
    # ERC-20, EIP-2612, EIP-5267, ownable
    "DOMAIN_SEPARATOR", "allowance", "approve", "balanceOf", "decimals",
    "eip712Domain", "name", "nonces", "owner", "permit", "symbol",
    "totalSupply", "transfer", "transferFrom",
    # CDP actions
    "burn", "buy_surplus", "cover_bad_debt", "deposit", "liquidate", "mint",
    "redeem", "withdraw",
    # CDP views
    "bad_debt", "collat_ratio", "collateral", "debt", "debt_shares",
    "last_accrual", "rate_index", "reserve", "surplus", "total_debt_shares",
    # Parameters
    "LIQUIDATION_PENALTY", "MAX_STABILITY_FEE", "MIN_COLLAT_RATIO", "ORACLE",
    "ORACLE_TIMEOUT", "REDEMPTION_FEE", "SEQUENCER_GRACE_PERIOD",
    "SEQUENCER_UPTIME_FEED", "STABILITY_FEE", "SWAP_FEE", "VARIANT",
}


@pytest.fixture(scope="module")
def stable(oracle, admin):
    with boa.env.prank(admin):
        return deploy_stable(oracle.address)


def _send(stable, sender, value, data=b""):
    return boa.env.raw_call(stable.address, sender=sender, value=value, data=data)


# ================= Plain transfers =================


def test_plain_transfer_is_a_deposit(stable, borrower):
    """Money Flow: borrower ETH → ministable, with no calldata."""
    borrower_eth = boa.env.get_balance(borrower)

    computation = _send(stable, borrower, ETH)
    logs = filter_logs(stable, "Deposit", computation)

    assert stable.collateral(borrower) == ETH
    assert boa.env.get_balance(stable.address) == ETH
    assert boa.env.get_balance(borrower) == borrower_eth - ETH
    assert len(logs) == 1
    assert (logs[0].user, logs[0].amount) == (borrower, ETH)


def test_plain_transfer_of_zero_reverts(stable, borrower):
    # `boa.reverts` only catches calls made through a contract wrapper.
    with pytest.raises(Revert):
        _send(stable, borrower, 0)


def test_plain_transfers_accumulate_with_deposits(stable, borrower):
    _send(stable, borrower, ETH)
    stable.deposit(value=2 * ETH, sender=borrower)
    _send(stable, borrower, 3 * ETH)

    assert stable.collateral(borrower) == 6 * ETH
    assert boa.env.get_balance(stable.address) == 6 * ETH


def test_unknown_selector_with_value_is_a_deposit(stable, borrower):
    """`__default__` catches any calldata it does not recognise, so ETH sent
    with a mistyped call is credited, not lost."""
    _send(stable, borrower, ETH, data=bytes.fromhex("deadbeef"))

    assert stable.collateral(borrower) == ETH


def test_unknown_selector_without_value_reverts(stable, borrower):
    with pytest.raises(Revert):
        _send(stable, borrower, 0, data=bytes.fromhex("deadbeef"))


def test_contract_sender_is_credited(stable):
    """A smart wallet sending ETH is credited as itself, and can withdraw it."""
    wallet = MOCK_REENTRANT_CALLER.deploy(stable.address)

    wallet.forward(b"", value=ETH)
    assert stable.collateral(wallet.address) == ETH

    wallet.forward(stable.withdraw.prepare_calldata(ETH))
    assert stable.collateral(wallet.address) == 0
    assert boa.env.get_balance(wallet.address) == ETH


def test_plain_transfer_rescues_position(stable, oracle, borrower, liquidator):
    """A borrower about to be liquidated can top up with a plain transfer."""
    _send(stable, borrower, POSITION_COLLATERAL)
    stable.mint(POSITION_DEBT, sender=borrower)
    oracle.set_answer(to_feed_price(1400))
    assert stable.collat_ratio(borrower) < MIN_COLLAT_RATIO

    _send(stable, borrower, ETH)

    assert stable.collat_ratio(borrower) >= MIN_COLLAT_RATIO
    with boa.reverts(dev="[cdp] position healthy"):
        stable.liquidate(borrower, MAX_UINT256, sender=liquidator)


# ================= Lifecycle on the production contract =================


def test_full_lifecycle(stable, oracle, borrower, liquidator, recipient):
    """Deposit by transfer, mint, move mUSD, get redeemed and liquidated, repay
    and exit, all on the deployed contract."""
    _send(stable, borrower, 2 * ETH)
    limit = max_mintable(2 * ETH, oracle.answer())
    stable.mint(limit, sender=borrower)
    assert stable.balanceOf(borrower) == limit
    with boa.reverts(dev="[cdp] undercollateralized"):
        stable.withdraw(1, sender=borrower)

    # Someone else holds mUSD and redeems against the borrower.
    stable.transfer(recipient, 500 * ETH, sender=borrower)
    stable.redeem(borrower, 500 * ETH, sender=recipient)
    assert stable.debt(borrower) == limit - 500 * ETH

    # A liquidator mints its own mUSD and brings the position back to 150%.
    stable.deposit(value=10 * ETH, sender=liquidator)
    stable.mint(5_000 * ETH, sender=liquidator)
    oracle.set_answer(to_feed_price(1700))
    stable.liquidate(borrower, MAX_UINT256, sender=liquidator)
    assert stable.collat_ratio(borrower) >= MIN_COLLAT_RATIO

    # The borrower still holds the mUSD the liquidator repaid for them, so
    # they can clear the rest of the debt and leave with what is left.
    debt = stable.debt(borrower)
    assert stable.balanceOf(borrower) >= debt
    stable.burn(debt, sender=borrower)
    collateral = stable.collateral(borrower)
    stable.withdraw(collateral, sender=borrower)

    assert stable.debt(borrower) == 0
    assert stable.collateral(borrower) == 0
    assert boa.env.get_balance(stable.address) == stable.collateral(liquidator)


# ================= Deployment =================


def test_exact_external_interface(stable):
    functions = [x["name"] for x in stable.abi if x["type"] == "function"]

    assert set(functions) == EXPECTED_FUNCTIONS
    # `redeem` has an overload for its default `min_paid`; nothing else does.
    assert sorted(f for f in functions if functions.count(f) > 1) == ["redeem", "redeem"]


def test_has_no_admin_functions(stable):
    """The owner exists only as the deployer's record: nothing can change
    the parameters, pause, or move funds after deployment."""
    functions = {x["name"] for x in stable.abi if x["type"] == "function"}

    assert not functions & {
        "transfer_ownership", "renounce_ownership", "set_oracle", "pause",
        "set_stability_fee", "sweep", "upgrade",
    }


def test_constructor_parameters(admin):
    oracle = MOCK_AGGREGATOR.deploy(to_feed_price(2000), 8)
    sequencer = MOCK_AGGREGATOR.deploy(0, 0)
    with boa.env.prank(admin):
        stable = ministable.deploy(
            "Moon USD", "MOON", 18, "Moon USD", "2",
            oracle.address, 2400, sequencer.address, MAX_STABILITY_FEE,
        )

    assert (stable.name(), stable.symbol(), stable.decimals()) == ("Moon USD", "MOON", 18)
    assert stable.eip712Domain()[1:3] == ("Moon USD", "2")
    assert stable.ORACLE() == oracle.address
    assert stable.ORACLE_TIMEOUT() == 2400
    assert stable.SEQUENCER_UPTIME_FEED() == sequencer.address
    assert stable.STABILITY_FEE() == MAX_STABILITY_FEE
    assert stable.VARIANT() == VARIANT_NATIVE
    assert stable.owner() == admin
    assert stable.totalSupply() == 0
    assert boa.env.get_balance(stable.address) == 0


def test_stability_fee_above_cap_reverts(oracle):
    with boa.reverts(dev="[cdp] stability fee too high"):
        deploy_stable(oracle.address, fee=MAX_STABILITY_FEE + 1)


def test_zero_oracle_timeout_reverts(oracle):
    with boa.reverts(dev="[cdp] zero oracle timeout"):
        deploy_stable(oracle.address, timeout=0)


def test_default_deploy_has_no_sequencer(stable):
    assert stable.SEQUENCER_UPTIME_FEED() == ZERO_ADDRESS
    assert stable.ORACLE_TIMEOUT() == ORACLE_TIMEOUT
