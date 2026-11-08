"""Verify an already-deployed mUSD on the block explorer.

    mox run verify --network arbitrum

Targets the latest mUSD deployment moccasin recorded for the network
(in .deployments.db), e.g. when `mox run deploy` succeeded but verification
failed. Sends no transactions.
"""

from moccasin.boa_tools import VyperContract
from moccasin.config import get_active_network

from script.deploy import (
    _check_deployment,
    _constructor_args,
    _get_price_feed,
    _get_sequencer_feed,
    _oracle_timeout,
    _require,
    _stability_fee,
    _verify,
)
from src import mUSD


def verify() -> VyperContract:
    network = get_active_network()
    deployed = network.get_latest_contract_unchecked("mUSD")
    _require(
        deployed is not None,
        f"No mUSD deployment recorded for network '{network.name}'.",
    )

    stable: VyperContract = mUSD.at(deployed.address)
    feed = _get_price_feed(network)
    timeout = _oracle_timeout(network)
    sequencer = _get_sequencer_feed(network)
    stability_fee = _stability_fee(network)
    # `at()` doesn't know the constructor arguments, which the explorer needs
    # to match the creation bytecode. `_check_deployment` confirms they agree
    # with the on-chain state.
    stable.ctor_calldata = stable._ctor.prepare_calldata(
        *_constructor_args(feed, timeout, sequencer, stability_fee)
    )
    _check_deployment(stable, feed, timeout, sequencer, stability_fee)
    print(f"Verifying mUSD at {stable.address} on '{network.name}'")

    _verify(network, stable)
    return stable


def moccasin_main() -> VyperContract:
    return verify()
