# pragma version ~=0.4.3
# pragma nonreentrancy on
"""
@title Test harness for the `cdp_erc20` module
@notice Wires `cdp_erc20` into a stablecoin the same way
        `src/mUSD.vy` wires `cdp_native`, so the
        module can be tested before a production contract
        uses it.
"""


from ethereum.ercs import IERC20


from modules.cdp.interfaces import IAggregatorV3


from snekmate.auth import ownable as ow
initializes: ow


from modules.tokens import erc20
initializes: erc20[ownable := ow]


from modules.cdp import cdp_erc20
initializes: cdp_erc20


exports: (
    erc20.__interface__,
    cdp_erc20.__interface__,
)


@deploy
def __init__(
    collateral_: IERC20,
    oracle: IAggregatorV3,
    oracle_timeout_: uint256,
    sequencer_uptime_feed_: IAggregatorV3,
    stability_fee_: uint256,
):
    ow.__init__()
    erc20.__init__("ministable", "mUSD", 18, "ministable", "1")
    cdp_erc20.__init__(
        collateral_, oracle, oracle_timeout_, sequencer_uptime_feed_, stability_fee_
    )
