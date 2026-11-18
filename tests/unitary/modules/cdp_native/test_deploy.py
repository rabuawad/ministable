import boa

from tests.utils.constants import (
    LIQUIDATION_PENALTY,
    MAX_STABILITY_FEE,
    MIN_COLLAT_RATIO,
    ORACLE_TIMEOUT,
    PRECISION,
    REDEMPTION_FEE,
    SWAP_FEE,
    SEQUENCER_GRACE_PERIOD,
    VARIANT_NATIVE,
    ZERO_ADDRESS,
)


def test_parameters(cdp, oracle):
    assert cdp.ORACLE() == oracle.address
    assert cdp.ORACLE_TIMEOUT() == ORACLE_TIMEOUT
    assert cdp.SEQUENCER_UPTIME_FEED() == ZERO_ADDRESS
    assert cdp.STABILITY_FEE() == 0
    assert cdp.VARIANT() == VARIANT_NATIVE


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
