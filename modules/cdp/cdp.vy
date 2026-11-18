# pragma version ~=0.4.3
# pragma nonreentrancy on
"""
@title Collateral-Agnostic CDP Engine
@custom:contract-name cdp
@notice The accounting shared by every CDP module: positions,
        debt shares, the stability fee, liquidations, bad debt,
        redemptions, the surplus and the oracle. Users mint the
        stablecoin against their collateral at a minimum 150%
        collateral ratio. Debt accrues a fixed stability fee,
        minted to the protocol's surplus. Positions below 150%
        can be liquidated back to 150%: the liquidator repays
        debt and receives 110% of it in collateral. Debt that a
        position's collateral cannot cover becomes bad debt,
        which the surplus and reserve absorb. Anyone can redeem
        the stablecoin for $1 of collateral from a healthy
        position.

        This module never moves collateral. Its internal
        functions update the accounting and return the
        collateral to pay out; the module wrapping it (e.g.
        `cdp_native`, `cdp_erc20`) receives and sends the
        collateral itself, after the accounting is done.
@license GNU Affero General Public License v3.0 only
@author rafael-abuawad
"""


# @dev We import the `IAggregatorV3` interface
# for the Chainlink collateral / FIAT price feed.
from .interfaces import IAggregatorV3


# @dev We import and use the `erc20` module,
# which tracks the stablecoin minted against
# the collateral.
from ..tokens import erc20
uses: erc20


# @dev The kind of collateral backing the positions,
# set by the module wrapping this one. `NATIVE` is the
# chain's native cryptocurrency (`cdp_native`); `ERC20`
# is an ERC-20 token (`cdp_erc20`).
flag Variant:
    NATIVE
    ERC20


# @dev Minimum collateral ratio, 1e18-scaled (150%).
MIN_COLLAT_RATIO: public(constant(uint256)) = 15 * 10**17


# @dev Time the L2 sequencer must have been back up
# before prices are trusted again, in seconds.
SEQUENCER_GRACE_PERIOD: public(constant(uint256)) = 3600


# @dev Collateral a liquidator receives per mSTABLE repaid, valued
# at the oracle price, 1e18-scaled (110%: a 10% bonus).
LIQUIDATION_PENALTY: public(constant(uint256)) = 11 * 10**17


# @dev Share of a redemption's collateral left with the borrower
# whose position is redeemed, at a 150% ratio, 1e18-scaled (0.5%).
# The fee rises with the ratio, so redeemers reach for the riskiest
# positions first and safer borrowers are paid more when redeemed.
REDEMPTION_FEE: public(constant(uint256)) = 5 * 10**15


# @dev Extra redemption fee per 100% of collateral ratio above
# `MIN_COLLAT_RATIO`, 1e18-scaled (1%).
REDEMPTION_FEE_SLOPE: public(constant(uint256)) = 10**16


# @dev Cap on the redemption fee, reached at a 600% ratio,
# 1e18-scaled (5%). It keeps every healthy position redeemable,
# so the peg floor never drops below $0.95.
MAX_REDEMPTION_FEE: public(constant(uint256)) = 5 * 10**16


# @dev Spread the protocol keeps when it sells surplus mSTABLE or pays
# reserve collateral for bad debt, 1e18-scaled (0.5%). Without it,
# a caller trades at a lagging oracle price and takes the lag.
SWAP_FEE: public(constant(uint256)) = 5 * 10**15


# @dev Largest allowed stability fee: 10% a year, as a
# 1e18-scaled per-second rate.
MAX_STABILITY_FEE: public(constant(uint256)) = 10**17 // (365 * 86400)


# @dev Constant to calculate the precision.
PRECISION: constant(uint256) = 10**18


# @dev The collateral / FIAT price feed.
ORACLE: public(immutable(IAggregatorV3))


# @dev Maximum age of an oracle answer, in seconds.
# Set per network at deployment: the feed's heartbeat
# plus a buffer.
ORACLE_TIMEOUT: public(immutable(uint256))


# @dev Scales an oracle answer to the 1e18-scaled FIAT
# value of 1e18 base units of the collateral, so that
# `amount * _price() // 1e18` is the FIAT value of
# `amount` base units at 18 decimals, whatever the
# decimals of the collateral and the feed.
PRICE_SCALE: immutable(uint256)


# @dev The Chainlink L2 sequencer uptime feed, or
# `empty(address)` on networks without a sequencer.
SEQUENCER_UPTIME_FEED: public(immutable(IAggregatorV3))


# @dev Interest charged on debt, as a 1e18-scaled
# per-second rate. Fixed at deployment.
STABILITY_FEE: public(immutable(uint256))


# @dev The kind of collateral backing the positions:
# exactly one member of `Variant`. Fixed at deployment.
VARIANT: public(immutable(Variant))


# @dev Returns the collateral (in base units)
# locked by an `address`.
collateral: public(HashMap[address, uint256])


# @dev Returns the normalised debt of an `address`.
# Its debt in mSTABLE is `debt_shares * rate_index / 1e18`.
debt_shares: public(HashMap[address, uint256])


# @dev Returns the sum of all `debt_shares`.
total_debt_shares: public(uint256)


# @dev Returns the 1e18-scaled interest index. It starts
# at 1e18 and grows by `STABILITY_FEE` every second.
rate_index: public(uint256)


# @dev Returns when `rate_index` was last updated.
last_accrual: public(uint256)


# @dev Returns the collateral (in base units)
# paid for surplus mSTABLE.
reserve: public(uint256)


# @dev Returns the mSTABLE in circulation that no position
# owes: debt written off when a position's collateral could not
# cover it, not yet absorbed by the surplus or reserve.
bad_debt: public(uint256)


# @dev Emitted when `user` locks `amount` base
# units of collateral.
event Deposit:
    user: indexed(address)
    amount: uint256


# @dev Emitted when `user` withdraws `amount`
# base units of collateral.
event Withdraw:
    user: indexed(address)
    amount: uint256


# @dev Emitted when `user` mints `amount` mSTABLE
# against their collateral.
event Mint:
    user: indexed(address)
    amount: uint256


# @dev Emitted when `user` burns `amount` mSTABLE
# to repay their debt.
event Burn:
    user: indexed(address)
    amount: uint256


# @dev Emitted when `amount` mSTABLE of interest is
# minted to the surplus.
event Accrue:
    amount: uint256


# @dev Emitted when `buyer` pays `paid` base units of
# collateral for `amount` mSTABLE from the surplus.
event BuySurplus:
    buyer: indexed(address)
    paid: uint256
    amount: uint256


# @dev Emitted when `liquidator` burns `repaid` mSTABLE
# of `user`'s debt and receives `seized` base units of
# their collateral. `written_off` is debt the collateral
# could not cover, moved to `bad_debt`.
event Liquidate:
    liquidator: indexed(address)
    user: indexed(address)
    repaid: uint256
    seized: uint256
    written_off: uint256


# @dev Emitted when `redeemer` burns `amount` mSTABLE of
# `user`'s debt and receives `paid` base units of their
# collateral.
event Redeem:
    redeemer: indexed(address)
    user: indexed(address)
    amount: uint256
    paid: uint256


# @dev Emitted when `amount` mSTABLE of surplus is burned
# against bad debt.
event Settle:
    amount: uint256


# @dev Emitted when `caller` burns `amount` mSTABLE of
# bad debt and receives `paid` base units of collateral
# from the reserve.
event CoverBadDebt:
    caller: indexed(address)
    amount: uint256
    paid: uint256


@deploy
def __init__(
    oracle: IAggregatorV3,
    oracle_timeout_: uint256,
    sequencer_uptime_feed_: IAggregatorV3,
    stability_fee_: uint256,
    collateral_decimals: uint8,
    variant_: Variant,
):
    assert variant_ == Variant.NATIVE or variant_ == Variant.ERC20 # dev: [cdp] invalid variant
    assert collateral_decimals <= 18 # dev: [cdp] unsupported collateral decimals
    # @dev Coarser units floor the collateral `_liquidate` seizes
    # to zero, so small shortfalls could never be liquidated.
    assert collateral_decimals >= 6 # dev: [cdp] unsupported collateral decimals
    assert oracle_timeout_ > 0 # dev: [cdp] zero oracle timeout
    oracle_decimals: uint8 = staticcall oracle.decimals()
    assert oracle_decimals <= 18 # dev: [cdp] unsupported oracle decimals
    ORACLE = oracle
    ORACLE_TIMEOUT = oracle_timeout_
    PRICE_SCALE = 10 ** (36 - convert(oracle_decimals, uint256) - convert(collateral_decimals, uint256))
    SEQUENCER_UPTIME_FEED = sequencer_uptime_feed_
    VARIANT = variant_
    assert stability_fee_ <= MAX_STABILITY_FEE # dev: [cdp] stability fee too high
    STABILITY_FEE = stability_fee_
    self.rate_index = PRECISION
    self.last_accrual = block.timestamp


# @dev Mints `amount` mSTABLE against the caller's collateral.
@external
def mint(amount: uint256):
    self._accrue()
    shares: uint256 = self._shares_up(amount)
    self.debt_shares[msg.sender] += shares
    self.total_debt_shares += shares
    assert self._collat_ratio(msg.sender) >= MIN_COLLAT_RATIO # dev: [cdp] undercollateralized
    erc20._mint(msg.sender, amount)
    log Mint(user=msg.sender, amount=amount)


# @dev Burns `amount` mSTABLE to repay the caller's debt.
@external
def burn(amount: uint256):
    self._accrue()
    self._repay(msg.sender, amount)
    erc20._burn(msg.sender, amount)
    log Burn(user=msg.sender, amount=amount)


# @dev Returns the mSTABLE debt of `user`, interest included.
@view
@external
def debt(user: address) -> uint256:
    return self._debt(user)


# @dev Returns the mSTABLE held by the protocol: interest not
# yet sold or spent on bad debt.
@view
@external
def surplus() -> uint256:
    return erc20.balanceOf[self]


# @dev Returns the 1e18-scaled collateral ratio of `user`.
@view
@external
def collat_ratio(user: address) -> uint256:
    return self._collat_ratio(user)


# @dev Credits `amount` base units of collateral, already
# received, to `user`.
@internal
def _deposit(user: address, amount: uint256):
    assert amount > 0 # dev: [cdp] zero deposit
    self.collateral[user] += amount
    log Deposit(user=user, amount=amount)


# @dev Debits `amount` base units of collateral from `user`,
# who must stay above the minimum ratio. The caller sends
# the collateral.
@internal
def _withdraw(user: address, amount: uint256):
    self._accrue()
    self.collateral[user] -= amount
    assert self._collat_ratio(user) >= MIN_COLLAT_RATIO # dev: [cdp] undercollateralized
    log Withdraw(user=user, amount=amount)


# @dev Liquidates an undercollateralized `user`. `msg.sender`
# repays up to `max_repay` mSTABLE of their debt and is owed
# `LIQUIDATION_PENALTY` (110%) of it in collateral. Returns the
# mSTABLE repaid and the collateral seized, which the caller sends.
#
# If the collateral covers 110% of the debt, the liquidator
# repays only what brings the position back to 150%, and
# the borrower keeps the rest of their collateral. If it covers
# the debt but not 110% of it, the liquidator repays the whole
# debt and takes all of the collateral, so the bonus shrinks
# to zero at 100% and no debt is written off. Otherwise the
# liquidator repays what the collateral covers at 110%, takes
# all of it, and the rest of the debt becomes bad debt.
@internal
def _liquidate(user: address, max_repay: uint256) -> (uint256, uint256):
    self._accrue()
    assert self._collat_ratio(user) < MIN_COLLAT_RATIO # dev: [cdp] position healthy
    p: uint256 = self._price()
    d: uint256 = self._debt(user)
    c: uint256 = self.collateral[user]
    # @dev FIAT value of the collateral, 1e36-scaled. Floored
    # as in `_collat_ratio`, so `needed` below is positive.
    value: uint256 = c * p // PRECISION * PRECISION

    repay: uint256 = 0
    seized: uint256 = 0
    written_off: uint256 = 0
    if value >= LIQUIDATION_PENALTY * d:
        # @dev Solve (value - 1.1x) / (d - x) = 1.5 for x,
        # rounding up so the position ends at or above 150%.
        # The margins cover rounding after the repay: the
        # collateral value floors by up to 1 wei, and the debt
        # left, whose removed shares round down, exceeds `d - x`
        # by up to `rate_index / 1e18 + 1` wei.
        debt_margin: uint256 = self.rate_index // PRECISION + 1
        needed: uint256 = MIN_COLLAT_RATIO * (d + debt_margin) - value + PRECISION
        step: uint256 = MIN_COLLAT_RATIO - LIQUIDATION_PENALTY
        repay = min(min((needed + step - 1) // step, d), max_repay)
        assert repay > 0 # dev: [cdp] zero repay
        seized = min(repay * LIQUIDATION_PENALTY // p, c)
        self._repay(user, repay)
    else:
        if value >= d * PRECISION:
            repay = d
        else:
            repay = value // LIQUIDATION_PENALTY
        assert max_repay >= repay # dev: [cdp] repay too small
        seized = c
        written_off = d - repay
        self.total_debt_shares -= self.debt_shares[user]
        self.debt_shares[user] = 0
        self.bad_debt += written_off

    self.collateral[user] -= seized
    erc20._burn(msg.sender, repay)
    log Liquidate(liquidator=msg.sender, user=user, repaid=repay, seized=seized, written_off=written_off)
    self._settle()
    return repay, seized


# @dev Swaps `amount` of `msg.sender`'s mSTABLE for $1 of collateral
# per mSTABLE from `user`'s position, at the oracle price,
# less the redemption fee, which stays with the borrower.
# This puts a floor under the peg. Only healthy positions
# can be redeemed; the redeemer picks which, and pays
# more for safer ones. Reverts if the collateral owed is
# below `min_paid`. Returns the collateral owed, which the
# caller sends.
@internal
def _redeem(user: address, amount: uint256, min_paid: uint256) -> uint256:
    self._accrue()
    assert amount > 0 # dev: [cdp] zero redeem
    ratio: uint256 = self._collat_ratio(user)
    assert ratio >= MIN_COLLAT_RATIO # dev: [cdp] position unhealthy
    paid: uint256 = amount * (PRECISION - self._redemption_fee(ratio)) // self._price()
    assert paid >= min_paid # dev: [cdp] slippage
    self._repay(user, amount)
    self.collateral[user] -= paid
    erc20._burn(msg.sender, amount)
    log Redeem(redeemer=msg.sender, user=user, amount=amount, paid=paid)
    return paid


# @dev Burns `amount` mSTABLE of bad debt from `msg.sender` and
# takes its value in collateral from the reserve, at the
# oracle price, less `SWAP_FEE`, which stays in the reserve.
# Returns the collateral owed, which the caller sends.
@internal
def _cover_bad_debt(amount: uint256) -> uint256:
    self._accrue()
    assert amount > 0 # dev: [cdp] zero cover
    assert amount <= self.bad_debt # dev: [cdp] cover exceeds bad debt
    paid: uint256 = amount * (PRECISION - SWAP_FEE) // self._price()
    assert paid <= self.reserve # dev: [cdp] not enough reserve
    self.bad_debt -= amount
    self.reserve -= paid
    erc20._burn(msg.sender, amount)
    log CoverBadDebt(caller=msg.sender, amount=amount, paid=paid)
    return paid


# @dev Sells surplus mSTABLE to `msg.sender` for `paid` base units
# of collateral, already received, at the oracle price, less
# `SWAP_FEE`. Interest is minted to the surplus, so this is
# how it reaches borrowers who need it to repay. The collateral
# paid is kept in the reserve. Returns the mSTABLE bought.
@internal
def _buy_surplus(paid: uint256) -> uint256:
    self._accrue()
    bought: uint256 = paid * self._price() // PRECISION * (PRECISION - SWAP_FEE) // PRECISION
    assert bought > 0 # dev: [cdp] zero purchase
    assert bought <= erc20.balanceOf[self] # dev: [cdp] not enough surplus
    self.reserve += paid
    erc20._transfer(self, msg.sender, bought)
    log BuySurplus(buyer=msg.sender, paid=paid, amount=bought)
    return bought


# @dev Brings `rate_index` up to date and mints the
# interest owed since the last update to the surplus.
@internal
def _accrue():
    index: uint256 = self._rate_index()
    if index == self.rate_index:
        return
    fee: uint256 = self.total_debt_shares * (index - self.rate_index) // PRECISION
    self.rate_index = index
    self.last_accrual = block.timestamp
    if fee > 0:
        erc20._mint(self, fee)
        log Accrue(amount=fee)
        self._settle()


# @dev Burns surplus mSTABLE against bad debt.
@internal
def _settle():
    amount: uint256 = min(erc20.balanceOf[self], self.bad_debt)
    if amount == 0:
        return
    self.bad_debt -= amount
    erc20._burn(self, amount)
    log Settle(amount=amount)


# @dev Cuts `user`'s debt by `amount` mSTABLE. Repaying the
# whole debt clears every share; a partial repay rounds the
# shares removed down, in the protocol's favour.
@internal
def _repay(user: address, amount: uint256):
    d: uint256 = self._debt(user)
    assert amount <= d # dev: [cdp] repay exceeds debt
    shares: uint256 = self.debt_shares[user]
    if amount < d:
        shares = amount * PRECISION // self.rate_index
    self.debt_shares[user] -= shares
    self.total_debt_shares -= shares


# @dev The current interest index, including interest not
# yet accrued.
@view
@internal
def _rate_index() -> uint256:
    elapsed: uint256 = block.timestamp - self.last_accrual
    return self.rate_index + self.rate_index * STABILITY_FEE * elapsed // PRECISION


# @dev Shares that represent `amount` mSTABLE of new debt,
# rounded up in the protocol's favour.
@view
@internal
def _shares_up(amount: uint256) -> uint256:
    index: uint256 = self.rate_index
    return (amount * PRECISION + index - 1) // index


# @dev `user`'s debt in mSTABLE, rounded up.
@view
@internal
def _debt(user: address) -> uint256:
    return (self.debt_shares[user] * self._rate_index() + PRECISION - 1) // PRECISION


# @dev The 1e18-scaled FIAT value of 1e18 base units of
# the collateral. For 18-decimal collateral this is its
# FIAT price at 18 decimals.
@view
@internal
def _price() -> uint256:
    if SEQUENCER_UPTIME_FEED.address != empty(address):
        self._check_sequencer()

    round_id: uint80 = 0
    answer: int256 = 0
    started_at: uint256 = 0
    updated_at: uint256 = 0
    answered_in_round: uint80 = 0
    round_id, answer, started_at, updated_at, answered_in_round = staticcall ORACLE.latestRoundData()
    assert answer > 0 # dev: [cdp] invalid price
    assert block.timestamp - updated_at <= ORACLE_TIMEOUT # dev: [cdp] stale price
    return convert(answer, uint256) * PRICE_SCALE


# @dev Reverts while the L2 sequencer is down, and for
# `SEQUENCER_GRACE_PERIOD` seconds after it comes back,
# so positions aren't liquidated on prices users could
# not react to.
@view
@internal
def _check_sequencer():
    round_id: uint80 = 0
    answer: int256 = 0
    started_at: uint256 = 0
    updated_at: uint256 = 0
    answered_in_round: uint80 = 0
    round_id, answer, started_at, updated_at, answered_in_round = staticcall SEQUENCER_UPTIME_FEED.latestRoundData()
    # @dev 0 means up, 1 means down.
    assert answer == 0 # dev: [cdp] sequencer down
    # @dev Arbitrum reports 0 before the feed is initialised.
    assert started_at > 0 # dev: [cdp] sequencer down
    assert block.timestamp - started_at > SEQUENCER_GRACE_PERIOD # dev: [cdp] sequencer grace period


@view
@internal
def _collat_ratio(user: address) -> uint256:
    d: uint256 = self._debt(user)
    if d == 0:
        return max_value(uint256)
    value: uint256 = self.collateral[user] * self._price() // PRECISION
    return value * PRECISION // d


# @dev The 1e18-scaled redemption fee for a position at
# `ratio`: `REDEMPTION_FEE` at 150%, plus `REDEMPTION_FEE_SLOPE`
# per 100% above it, up to `MAX_REDEMPTION_FEE`. The excess
# is capped before it is scaled, so a debt-free position's
# `max_value(uint256)` ratio cannot overflow.
@pure
@internal
def _redemption_fee(ratio: uint256) -> uint256:
    excess: uint256 = min(
        ratio - MIN_COLLAT_RATIO,
        (MAX_REDEMPTION_FEE - REDEMPTION_FEE) * PRECISION // REDEMPTION_FEE_SLOPE,
    )
    return REDEMPTION_FEE + excess * REDEMPTION_FEE_SLOPE // PRECISION
