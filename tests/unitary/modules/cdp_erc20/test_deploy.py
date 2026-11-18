import boa
import pytest

from tests.mocks.deployers import MOCK_AGGREGATOR, MOCK_TOKEN
from tests.utils.constants import (
    LIQUIDATION_PENALTY,
    MAX_STABILITY_FEE,
    MIN_COLLAT_RATIO,
    ORACLE_TIMEOUT,
    PRECISION,
    REDEMPTION_FEE,
    SWAP_FEE,
    SEQUENCER_GRACE_PERIOD,
    VARIANT_ERC20,
    ZERO_ADDRESS,
)
from tests.utils.helpers import deploy_cdp_erc20, to_feed_price


def test_parameters(cdp, token, oracle):
    assert cdp.COLLATERAL() == token.address
    assert cdp.ORACLE() == oracle.address
    assert cdp.ORACLE_TIMEOUT() == ORACLE_TIMEOUT
    assert cdp.SEQUENCER_UPTIME_FEED() == ZERO_ADDRESS
    assert cdp.STABILITY_FEE() == 0
    assert cdp.VARIANT() == VARIANT_ERC20


def test_constants(cdp):
    assert cdp.MIN_COLLAT_RATIO() == MIN_COLLAT_RATIO
    assert cdp.SEQUENCER_GRACE_PERIOD() == SEQUENCER_GRACE_PERIOD
    assert cdp.LIQUIDATION_PENALTY() == LIQUIDATION_PENALTY
    assert cdp.REDEMPTION_FEE() == REDEMPTION_FEE
    assert cdp.SWAP_FEE() == SWAP_FEE
    assert cdp.MAX_STABILITY_FEE() == MAX_STABILITY_FEE


def test_initial_state(cdp):
    assert cdp.rate_index() == PRECISION
    assert cdp.last_accrual() == boa.env.evm.patch.timestamp
    assert cdp.total_debt_shares() == 0
    assert cdp.reserve() == 0
    assert cdp.bad_debt() == 0
    assert cdp.surplus() == 0
    assert cdp.totalSupply() == 0


def test_stablecoin_metadata(cdp):
    assert cdp.name() == "ministable"
    assert cdp.symbol() == "mUSD"
    assert cdp.decimals() == 18


def test_max_stability_fee_accepted(token, oracle):
    cdp = deploy_cdp_erc20(token.address, oracle.address, fee=MAX_STABILITY_FEE)

    assert cdp.STABILITY_FEE() == MAX_STABILITY_FEE


def test_stability_fee_above_cap_reverts(token, oracle):
    with boa.reverts(dev="[cdp] stability fee too high"):
        deploy_cdp_erc20(token.address, oracle.address, fee=MAX_STABILITY_FEE + 1)


def test_zero_oracle_timeout_reverts(token, oracle):
    with boa.reverts(dev="[cdp] zero oracle timeout"):
        deploy_cdp_erc20(token.address, oracle.address, timeout=0)


def test_collateral_with_more_than_18_decimals_reverts(oracle):
    token = MOCK_TOKEN.deploy(19)

    with boa.reverts(dev="[cdp] unsupported collateral decimals"):
        deploy_cdp_erc20(token.address, oracle.address)


@pytest.mark.parametrize("decimals", [0, 2, 5])
def test_collateral_with_fewer_than_6_decimals_reverts(oracle, decimals):
    """Coarser units would floor the collateral a liquidation seizes to zero."""
    token = MOCK_TOKEN.deploy(decimals)

    with boa.reverts(dev="[cdp] unsupported collateral decimals"):
        deploy_cdp_erc20(token.address, oracle.address)


def test_collateral_with_6_and_18_decimals_accepted(oracle):
    for decimals in (6, 18):
        token = MOCK_TOKEN.deploy(decimals)
        deploy_cdp_erc20(token.address, oracle.address)


def test_feed_with_more_than_18_decimals_reverts(token):
    feed = MOCK_AGGREGATOR.deploy(to_feed_price(2000, 19), 19)

    with boa.reverts(dev="[cdp] unsupported oracle decimals"):
        deploy_cdp_erc20(token.address, feed.address)


def test_collateral_without_code_reverts(oracle):
    """`decimals()` on an address with no code cannot be decoded."""
    with boa.reverts():
        deploy_cdp_erc20(boa.env.generate_address("not a token"), oracle.address)
