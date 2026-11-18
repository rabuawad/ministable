# pragma version ~=0.4.3
# pragma nonreentrancy on
"""
@title CDP Engine Backed by an ERC-20 Token
@custom:contract-name cdp_erc20
@notice Users lock an ERC-20 collateral token (e.g. USDC,
        USDT, WETH) via `deposit` and mint the stablecoin
        against it at a minimum 150% collateral ratio. The
        accounting lives in the `cdp` module; this module
        pulls and sends the collateral token.

        The collateral token must have 6 to 18 decimals and
        may omit the `bool` return value on `transfer` and
        `transferFrom` (as USDT does). Deposits credit the
        balance the contract actually received, so tokens
        that charge a fee on transfer are accounted for.
        Rebasing tokens are not supported: a negative rebase
        would leave the contract holding less than it owes.
@license GNU Affero General Public License v3.0 only
@author rafael-abuawad
"""


# @dev We import the `IERC20` interface, which is
# a built-in interface of the Vyper compiler, for
# the collateral token.
from ethereum.ercs import IERC20


# @dev We import the `IERC20Detailed` interface, which
# is a built-in interface of the Vyper compiler, to read
# the collateral token's decimals.
from ethereum.ercs import IERC20Detailed


# @dev We import the `IAggregatorV3` interface
# for the Chainlink collateral / USD price feed.
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


# @dev The ERC-20 token locked as collateral.
COLLATERAL: public(immutable(IERC20))


@deploy
def __init__(
    collateral_: IERC20,
    oracle: IAggregatorV3,
    oracle_timeout_: uint256,
    sequencer_uptime_feed_: IAggregatorV3,
    stability_fee_: uint256,
):
    # @dev The stablecoin cannot back itself.
    assert collateral_.address != self # dev: [cdp_erc20] invalid collateral
    collateral_decimals: uint8 = staticcall IERC20Detailed(collateral_.address).decimals()
    COLLATERAL = collateral_
    # @dev The token backs positions as `Variant.ERC20`.
    cdp.__init__(oracle, oracle_timeout_, sequencer_uptime_feed_, stability_fee_, collateral_decimals, cdp.Variant.ERC20)


# @dev Pulls `amount` base units of the collateral token from
# the caller, who must have approved this contract, and locks
# what arrives as their collateral. Returns the amount credited.
@external
def deposit(amount: uint256) -> uint256:
    assert amount > 0 # dev: [cdp_erc20] amount must be greater than zero (0).
    received: uint256 = self._pull(msg.sender, amount)
    cdp._deposit(msg.sender, received)
    return received


# @dev Withdraws `amount` base units of the caller's collateral.
@external
def withdraw(amount: uint256):
    assert amount > 0 # dev: [cdp_erc20] amount must be greater than zero (0).
    cdp._withdraw(msg.sender, amount)
    self._push(msg.sender, amount)


# @dev Liquidates an undercollateralized `user`, repaying up
# to `max_repay` mUSD of their debt for 110% of it in
# collateral. A partial liquidation must retire at least one debt
# share at the accrued rate. Returns the mUSD repaid.
@external
def liquidate(user: address, max_repay: uint256) -> uint256:
    assert user != empty(address) # dev: [cdp_erc20] cannot liquidate the zero address.
    assert max_repay > 0 # dev: [cdp_erc20] max repay amount must be greater than zero (0).
    repay: uint256 = 0
    seized: uint256 = 0
    repay, seized = cdp._liquidate(user, max_repay)
    self._push(msg.sender, seized)
    return repay


# @dev Swaps `amount` of the caller's mUSD for $1 of collateral
# per mUSD from `user`'s healthy position, less the redemption
# fee. A partial redemption must retire at least one debt share
# and pay at least `min_paid` in collateral. See
# `cdp._redeem`. Returns the collateral paid, in base units.
@external
def redeem(user: address, amount: uint256, min_paid: uint256 = 0) -> uint256:
    assert user != empty(address) # dev: [cdp_erc20] cannot redeem the zero address.
    assert amount > 0 # dev: [cdp_erc20] amount must be greater than zero (0).
    assert min_paid > 0 # dev: [cdp_erc20] min paid amount must be greater than zero (0).
    paid: uint256 = cdp._redeem(user, amount, min_paid)
    self._push(msg.sender, paid)
    return paid


# @dev Burns `amount` mUSD of bad debt from the caller and
# pays them its value in collateral from the reserve, at the
# oracle price.
@external
def cover_bad_debt(amount: uint256) -> uint256:
    assert amount > 0 # dev: [cdp_erc20] amount must be greater than zero (0).
    paid: uint256 = cdp._cover_bad_debt(amount)
    self._push(msg.sender, paid)
    return paid


# @dev Sells surplus mUSD for `amount` base units of the
# collateral token, pulled from the caller, at the oracle
# price. The collateral paid is kept in the reserve.
@external
def buy_surplus(amount: uint256) -> uint256:
    assert amount > 0 # dev: [cdp_erc20] amount must be greater than zero (0).
    received: uint256 = self._pull(msg.sender, amount)
    return cdp._buy_surplus(received)


# @dev Pulls `amount` of the collateral token from `owner` and
# returns what this contract actually received, which is less
# than `amount` for tokens that charge a fee on transfer.
@internal
def _pull(owner: address, amount: uint256) -> uint256:
    before: uint256 = staticcall COLLATERAL.balanceOf(self)
    assert extcall COLLATERAL.transferFrom(owner, self, amount, default_return_value=True) # dev: [cdp_erc20] transfer failed
    return staticcall COLLATERAL.balanceOf(self) - before


# @dev Sends `amount` of the collateral token to `to`.
@internal
def _push(to: address, amount: uint256):
    assert extcall COLLATERAL.transfer(to, amount, default_return_value=True) # dev: [cdp_erc20] transfer failed
