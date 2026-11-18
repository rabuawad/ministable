# pragma version ~=0.4.3
# pragma nonreentrancy on
"""
@title CDP Engine Backed by the Native Coin
@custom:contract-name cdp_native
@notice Users lock the chain's native coin via `deposit` and
        mint the stablecoin against it at a minimum 150%
        collateral ratio. The accounting lives in the `cdp`
        module; this module receives and sends the native
        coin.
@license GNU Affero General Public License v3.0 only
@author rafael-abuawad
"""


# @dev We import the `IAggregatorV3` interface
# for the Chainlink native coin / USD price feed.
from .interfaces import IAggregatorV3


# @dev We import the `erc20` module, which tracks
# the stablecoin minted against the collateral, to
# hand it to the `cdp` module.
from ..tokens import erc20


# @dev We import and initialise the `cdp` module,
# which holds the positions and their accounting.
from . import cdp
initializes: cdp[erc20 := erc20]


# @dev We export the `external` functions and
# public getters of the `cdp` module.
exports: (
    cdp.mint,
    cdp.burn,
    cdp.debt,
    cdp.surplus,
    cdp.collat_ratio,
    cdp.MIN_COLLAT_RATIO,
    cdp.SEQUENCER_GRACE_PERIOD,
    cdp.LIQUIDATION_PENALTY,
    cdp.REDEMPTION_FEE,
    cdp.SWAP_FEE,
    cdp.MAX_STABILITY_FEE,
    cdp.ORACLE,
    cdp.ORACLE_TIMEOUT,
    cdp.SEQUENCER_UPTIME_FEED,
    cdp.STABILITY_FEE,
    cdp.VARIANT,
    cdp.collateral,
    cdp.debt_shares,
    cdp.total_debt_shares,
    cdp.rate_index,
    cdp.last_accrual,
    cdp.reserve,
    cdp.bad_debt,
)


@deploy
@payable
def __init__(
    oracle: IAggregatorV3,
    oracle_timeout_: uint256,
    sequencer_uptime_feed_: IAggregatorV3,
    stability_fee_: uint256,
):
    # @dev The native coin has 18 decimals and
    # backs positions as `Variant.NATIVE`.
    cdp.__init__(oracle, oracle_timeout_, sequencer_uptime_feed_, stability_fee_, 18, cdp.Variant.NATIVE)


# @dev Locks the sent native coin as collateral for `msg.sender`.
@payable
@external
def deposit():
    assert msg.value > 0 # dev: [cdp_native] msg.value must be greater than zero (0).
    cdp._deposit(msg.sender, msg.value)


# @dev Withdraws `amount` wei of the caller's collateral.
@external
def withdraw(amount: uint256):
    assert amount > 0 # dev: [cdp_native] amount must be greater than zero (0).
    cdp._withdraw(msg.sender, amount)
    raw_call(msg.sender, b"", value=amount)


# @dev Liquidates an undercollateralized `user`, repaying up
# to `max_repay` mUSD of their debt for 110% of it in
# collateral. A partial liquidation must retire at least one debt
# share at the accrued rate. Returns the mUSD repaid.
@external
def liquidate(user: address, max_repay: uint256) -> uint256:
    assert user != empty(address) # dev: [cdp_native] cannot liquidate the zero address.
    assert max_repay > 0 # dev: [cdp_native] max repay amount must be greater than zero (0).
    repay: uint256 = 0
    seized: uint256 = 0
    repay, seized = cdp._liquidate(user, max_repay)
    raw_call(msg.sender, b"", value=seized)
    return repay


# @dev Swaps `amount` of the caller's mUSD for $1 of collateral
# per mUSD from `user`'s healthy position, less the redemption
# fee. A partial redemption must retire at least one debt share
# and pay at least `min_paid` in collateral. See
# `cdp._redeem`. Returns the collateral paid, in wei.
@external
def redeem(user: address, amount: uint256, min_paid: uint256 = 0) -> uint256:
    assert user != empty(address) # dev: [cdp_native] cannot redeem the zero address.
    assert amount > 0 # dev: [cdp_native] amount must be greater than zero (0).
    assert min_paid > 0 # dev: [cdp_native] min paid amount must be greater than zero (0).
    paid: uint256 = cdp._redeem(user, amount, min_paid)
    raw_call(msg.sender, b"", value=paid)
    return paid


# @dev Burns `amount` mUSD of bad debt from the caller and
# pays them its value in native coin from the reserve, at the
# oracle price.
@external
def cover_bad_debt(amount: uint256) -> uint256:
    assert amount > 0 # dev: [cdp_native] amount must be greater than zero (0).
    paid: uint256 = cdp._cover_bad_debt(amount)
    raw_call(msg.sender, b"", value=paid)
    return paid


# @dev Sells surplus mUSD for the sent native coin at the oracle
# price. The coin paid is kept in the reserve.
@payable
@external
def buy_surplus() -> uint256:
    return cdp._buy_surplus(msg.value)


# @dev Credits `amount` wei, already received, to `user`.
@internal
def _deposit(user: address, amount: uint256):
    cdp._deposit(user, amount)
