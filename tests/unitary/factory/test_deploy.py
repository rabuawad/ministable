import boa
import pytest

from src import factory, ministable
from tests.mocks.deployers import MOCK_AGGREGATOR
from tests.utils.constants import (
    ETH,
    MAX_STABILITY_FEE,
    ORACLE_TIMEOUT,
    POSITION_DEBT,
    VARIANT_NATIVE,
    ZERO_ADDRESS,
)
from tests.utils.helpers import deploy_stable, filter_logs, to_feed_price

MAX_MINISTABLES = 64


@pytest.fixture(scope="module")
def blueprint():
    return ministable.deploy_as_blueprint()


@pytest.fixture
def stable_factory(blueprint, admin):
    with boa.env.prank(admin):
        return factory.deploy(blueprint.address)


def _deploy(stable_factory, oracle, sender):
    return stable_factory.deploy_ministable(
        "ministable",
        "mUSD",
        18,
        "ministable",
        "1",
        oracle.address,
        ORACLE_TIMEOUT,
        ZERO_ADDRESS,
        0,
        sender=sender,
    )


def test_deployer_is_owner(stable_factory, admin):
    assert stable_factory.owner() == admin
    assert stable_factory.pending_owner() == ZERO_ADDRESS


def test_blueprint_is_stored(stable_factory, blueprint):
    assert stable_factory.MINISTABLE_BLUEPRINT() == blueprint.address


def test_owner_deploys_ministable(stable_factory, oracle, admin):
    stable_address = _deploy(stable_factory, oracle, admin)
    logs = filter_logs(stable_factory, "MinistableDeployed")
    stable = ministable.at(stable_address)

    assert stable_factory.n_ministables() == 1
    assert stable_factory.ministables(0) == stable_address
    assert stable_factory.is_ministable(stable_address)
    assert stable.owner() == stable_factory.address
    assert stable.ORACLE() == oracle.address
    assert (stable.name(), stable.symbol(), stable.decimals()) == ("ministable", "mUSD", 18)

    assert len(logs) == 1
    assert logs[0].stable == stable_address
    assert logs[0].owner == admin


def test_deployed_ministable_accepts_collateral(stable_factory, oracle, admin, borrower):
    """Money Flow: borrower ETH → deployed ministable."""
    stable = ministable.at(_deploy(stable_factory, oracle, admin))

    stable.deposit(value=ETH, sender=borrower)

    assert stable.collateral(borrower) == ETH
    assert boa.env.get_balance(stable.address) == ETH


def test_stranger_cannot_deploy(stable_factory, oracle, borrower):
    with boa.reverts("ownable: caller is not the owner"):
        _deploy(stable_factory, oracle, borrower)


def test_ownership_transfers_in_two_steps(stable_factory, oracle, admin, borrower):
    successor = boa.env.generate_address("successor")

    stable_factory.transfer_ownership(successor, sender=admin)
    assert stable_factory.owner() == admin
    assert stable_factory.pending_owner() == successor

    with boa.reverts("ownable_2step: caller is not the new owner"):
        stable_factory.accept_ownership(sender=admin)
    with boa.reverts("ownable: caller is not the owner"):
        _deploy(stable_factory, oracle, successor)

    stable_factory.accept_ownership(sender=successor)

    assert stable_factory.owner() == successor
    assert stable_factory.pending_owner() == ZERO_ADDRESS
    assert stable_factory.is_ministable(_deploy(stable_factory, oracle, successor))
    with boa.reverts("ownable: caller is not the owner"):
        _deploy(stable_factory, oracle, admin)


def test_renounced_factory_cannot_deploy(stable_factory, oracle, admin):
    stable_factory.renounce_ownership(sender=admin)

    assert stable_factory.owner() == ZERO_ADDRESS
    with boa.reverts("ownable: caller is not the owner"):
        _deploy(stable_factory, oracle, admin)


def test_rejects_empty_blueprint(admin):
    with boa.reverts(dev="[factory] blueprint is not a contract"):
        factory.deploy(ZERO_ADDRESS, sender=admin)


def test_rejects_contract_without_blueprint_preamble(oracle, admin):
    implementation = deploy_stable(oracle.address)
    with boa.reverts(dev="[factory] not an erc-5202 blueprint"):
        factory.deploy(implementation.address, sender=admin)


def test_forwards_every_constructor_argument(stable_factory, admin):
    oracle = MOCK_AGGREGATOR.deploy(to_feed_price(2000), 8)
    sequencer = MOCK_AGGREGATOR.deploy(0, 0)

    stable = ministable.at(
        stable_factory.deploy_ministable(
            "Moon USD", "MOON", 18, "Moon USD", "2",
            oracle.address, 2400, sequencer.address, MAX_STABILITY_FEE,
            sender=admin,
        )
    )

    assert (stable.name(), stable.symbol(), stable.decimals()) == ("Moon USD", "MOON", 18)
    assert stable.eip712Domain()[1:3] == ("Moon USD", "2")
    assert stable.ORACLE() == oracle.address
    assert stable.ORACLE_TIMEOUT() == 2400
    assert stable.SEQUENCER_UPTIME_FEED() == sequencer.address
    assert stable.STABILITY_FEE() == MAX_STABILITY_FEE
    assert stable.VARIANT() == VARIANT_NATIVE
    assert stable.rate_index() == 10**18


def test_invalid_arguments_revert_the_deploy(stable_factory, oracle, admin):
    """The blueprint constructor's checks still apply, and nothing is recorded."""
    with boa.reverts():
        stable_factory.deploy_ministable(
            "ministable", "mUSD", 18, "ministable", "1",
            oracle.address, ORACLE_TIMEOUT, ZERO_ADDRESS, MAX_STABILITY_FEE + 1,
            sender=admin,
        )

    assert stable_factory.n_ministables() == 0


def test_deployments_are_independent(stable_factory, oracle, admin, borrower):
    first = ministable.at(_deploy(stable_factory, oracle, admin))
    second = ministable.at(_deploy(stable_factory, oracle, admin))

    first.deposit(value=2 * ETH, sender=borrower)
    first.mint(POSITION_DEBT, sender=borrower)

    assert first.address != second.address
    assert (stable_factory.ministables(0), stable_factory.ministables(1)) == (
        first.address,
        second.address,
    )
    assert second.collateral(borrower) == 0
    assert second.totalSupply() == 0
    # mUSD from one deployment is not accepted by another.
    with boa.reverts():
        second.burn(1, sender=borrower)


def test_unrelated_address_is_not_a_ministable(stable_factory, oracle):
    assert not stable_factory.is_ministable(oracle.address)
    assert not stable_factory.is_ministable(ZERO_ADDRESS)


def test_deployment_limit(stable_factory, oracle, admin):
    assert stable_factory.MAX_MINISTABLES() == MAX_MINISTABLES
    for _ in range(MAX_MINISTABLES):
        _deploy(stable_factory, oracle, admin)
    assert stable_factory.n_ministables() == MAX_MINISTABLES

    with boa.reverts(dev="[factory] deployment limit reached"):
        _deploy(stable_factory, oracle, admin)

    assert stable_factory.n_ministables() == MAX_MINISTABLES
