# pragma version ~=0.4.3
# pragma nonreentrancy on
"""
@title mUSD: stablecoin backed by the native coin
@custom:contract-name mUSD
@notice The CDP engine lives in the token itself, through the
        `cdp_native` module. Users lock the chain's native coin
        via `deposit` or a plain transfer, and mint mUSD
        against it at a minimum 150% collateral ratio.
@license GNU Affero General Public License v3.0 only
@author rafael-abuawad
"""


# @dev We import and implement the `IERC20` interface,
# which is a built-in interface of the Vyper compiler.
from ethereum.ercs import IERC20
implements: IERC20


# @dev We import and implement the `IERC20Detailed` interface,
# which is a built-in interface of the Vyper compiler.
from ethereum.ercs import IERC20Detailed
implements: IERC20Detailed


# @dev We import and implement the `IERC20Permit`
# interfacex.
from snekmate.tokens.interfaces import IERC20Permit
implements: IERC20Permit


# @dev We import and implement the `IERC5267` interface,
from snekmate.utils.interfaces import IERC5267
implements: IERC5267


# @dev We import the `IAggregatorV3` interface
# for the Chainlink native coin / USD price feed.
from modules.cdp.interfaces import IAggregatorV3


# @dev We import and initialise the `ownable` module.
from snekmate.auth import ownable as ow
initializes: ow


# @dev We import and initialise the `erc20` module.
from modules.tokens import erc20
initializes: erc20[ownable := ow]


# @dev We import and initialise the `cdp_native` module.
from modules.cdp import cdp_native
initializes: cdp_native


# @dev We export all `external` functions
# from the `erc20` and `cdp_native` modules.
exports: (
    erc20.__interface__,
    cdp_native.__interface__,
)


@deploy
@payable
def __init__(
    name_: String[25],
    symbol_: String[5],
    decimals_: uint8,
    name_eip712_: String[50],
    version_eip712_: String[20],
    oracle: IAggregatorV3,
    oracle_timeout_: uint256,
    sequencer_uptime_feed_: IAggregatorV3,
    stability_fee_: uint256,
):
    ow.__init__()
    erc20.__init__(name_, symbol_, decimals_, name_eip712_, version_eip712_)
    cdp_native.__init__(oracle, oracle_timeout_, sequencer_uptime_feed_, stability_fee_)


# @dev Plain native coin transfers are treated as deposits.
@payable
@external
def __default__():
    cdp_native._deposit(msg.sender, msg.value)
