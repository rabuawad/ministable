# pragma version ~=0.4.3
# pragma nonreentrancy on
"""
@title Test harness for the `cdp_native` module
@notice Wires `cdp_native` into a stablecoin the same way
        `src/mUSD.vy` does, minus the plain-transfer
        `__default__`, so the module is tested on its own.
"""


from modules.cdp.interfaces import IAggregatorV3


from snekmate.auth import ownable as ow
initializes: ow


from modules.tokens import erc20
initializes: erc20[ownable := ow]


from modules.cdp import cdp_native
initializes: cdp_native


exports: (
    erc20.__interface__,
    cdp_native.__interface__,
)


@deploy
@payable
def __init__(
    oracle: IAggregatorV3,
    oracle_timeout_: uint256,
    sequencer_uptime_feed_: IAggregatorV3,
    stability_fee_: uint256,
):
    ow.__init__()
    erc20.__init__("ministable", "mUSD", 18, "ministable", "1")
    cdp_native.__init__(oracle, oracle_timeout_, sequencer_uptime_feed_, stability_fee_)
