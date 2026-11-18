"""Stateful fuzzing: a reference model shadows the `cdp_native` module through random
deposits, mints, burns, withdrawals, transfers, price moves, interest,
surplus purchases, redemptions, partial and insolvent liquidations and
bad-debt cover."""

import os

import boa
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
)

from tests.mocks.deployers import MOCK_AGGREGATOR
from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    LIQUIDATION_PENALTY,
    MAX_STABILITY_FEE,
    MAX_UINT256,
    MIN_COLLAT_RATIO,
    ORACLE_DECIMALS,
    PRECISION,
    SWAP_FEE,
)
from tests.utils.helpers import deploy_cdp_native, liquidation, max_mintable, redemption_fee

N_ACTORS = 4
STARTING_ETH = 1_000 * ETH

# A keeper holding a large mUSD buffer, so liquidations can actually succeed
# instead of reverting for lack of mUSD. Its interest is what fills the
# surplus, so it is kept small enough for actors to buy the surplus out
# and leave bad debt for the reserve to cover.
KEEPER_ETH = 10_000 * ETH
KEEPER_DEBT = 10_000_000 * ETH  # 200% at $2000 with all of KEEPER_ETH locked

actor_st = st.integers(min_value=0, max_value=N_ACTORS - 1)
eth_amount_st = st.integers(min_value=1, max_value=50 * ETH)
musd_amount_st = st.integers(min_value=1, max_value=200_000 * ETH)
feed_price_st = st.integers(min_value=100 * 10**8, max_value=10_000 * 10**8)
max_repay_st = st.one_of(st.just(MAX_UINT256), st.integers(min_value=0, max_value=50_000 * ETH))


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


class SolvencyMachine(RuleBasedStateMachine):
    @initialize()
    def setup(self):
        self.oracle = MOCK_AGGREGATOR.deploy(ETH_USD_PRICE, ORACLE_DECIMALS)
        self.cdp = deploy_cdp_native(self.oracle.address, fee=MAX_STABILITY_FEE)
        self.feed_price = ETH_USD_PRICE
        self.actors = [boa.env.generate_address(f"actor{i}") for i in range(N_ACTORS)]
        for actor in self.actors:
            boa.env.set_balance(actor, STARTING_ETH)
        self.collateral = {a: 0 for a in self.actors}
        self.shares = {a: 0 for a in self.actors}
        self.balance = {a: 0 for a in self.actors}
        self.index = PRECISION
        self.last_accrual = boa.env.timestamp
        self.surplus = 0
        self.reserve = 0
        self.bad_debt = 0
        # Rounding lets debt run a few wei ahead of supply; count the steps.
        self.steps = 0

        self.keeper = boa.env.generate_address("keeper")
        boa.env.set_balance(self.keeper, KEEPER_ETH)
        self.cdp.deposit(value=KEEPER_ETH, sender=self.keeper)
        self.cdp.mint(KEEPER_DEBT, sender=self.keeper)
        self.collateral[self.keeper] = KEEPER_ETH
        self.shares[self.keeper] = KEEPER_DEBT
        self.balance[self.keeper] = KEEPER_DEBT
        self.liquidations = 0

    # ================= Model helpers =================

    def _index_now(self) -> int:
        elapsed = boa.env.timestamp - self.last_accrual
        return self.index + self.index * MAX_STABILITY_FEE * elapsed // PRECISION

    def _pending_fee(self) -> int:
        return sum(self.shares.values()) * (self._index_now() - self.index) // PRECISION

    def _after_accrual(self) -> tuple[int, int]:
        """(surplus, bad_debt) once `_accrue` has minted the pending fee and settled."""
        fee = self._pending_fee()
        if fee == 0:
            return self.surplus, self.bad_debt
        settled = min(self.surplus + fee, self.bad_debt)
        return self.surplus + fee - settled, self.bad_debt - settled

    def _surplus_now(self) -> int:
        return self._after_accrual()[0]

    def _accrue(self):
        """Mirror `_accrue`. Call only once the contract call has succeeded:
        a revert rolls the contract's accrual back, and interest compounds per accrual."""
        index = self._index_now()
        if index == self.index:
            return
        self.surplus, self.bad_debt = self._after_accrual()
        self.index = index
        self.last_accrual = boa.env.timestamp

    def _settle(self):
        settled = min(self.surplus, self.bad_debt)
        self.surplus -= settled
        self.bad_debt -= settled

    def _debt_of(self, shares: int) -> int:
        return _ceil_div(shares * self._index_now(), PRECISION)

    def _debt(self, actor) -> int:
        return self._debt_of(self.shares[actor])

    def _partial_repay_below_one_share(self, amount, debt) -> bool:
        return 0 < amount < debt and amount < self._debt_of(1)

    def _ratio(self, collateral: int, debt: int) -> int:
        if debt == 0:
            return 2**256 - 1
        value = collateral * self.feed_price * 10**10 // PRECISION
        return value * PRECISION // debt

    def _bought(self, eth: int) -> int:
        """mUSD that `eth` buys from the surplus (mirrors `_buy_surplus`)."""
        return eth * self.feed_price * 10**10 // PRECISION * (PRECISION - SWAP_FEE) // PRECISION

    def _underwater(self) -> list:
        return [
            a
            for a in self.actors
            if self._ratio(self.collateral[a], self._debt(a)) < MIN_COLLAT_RATIO
        ]

    def _try_mint(self, actor, amount) -> bool:
        """Mint if the model says the result stays healthy; check a revert otherwise."""
        new_shares = self.shares[actor] + _ceil_div(amount * PRECISION, self._index_now())
        healthy = (
            self._ratio(self.collateral[actor], self._debt_of(new_shares))
            >= MIN_COLLAT_RATIO
        )
        if healthy:
            self.cdp.mint(amount, sender=actor)
            self._accrue()
            self.shares[actor] = new_shares
            self.balance[actor] += amount
        else:
            with boa.reverts(dev="[cdp] undercollateralized"):
                self.cdp.mint(amount, sender=actor)
        return healthy

    # ================= Rules =================

    @rule(i=actor_st, amount=eth_amount_st)
    def deposit(self, i, amount):
        actor = self.actors[i]
        amount = min(amount, boa.env.get_balance(actor))
        if amount == 0:
            return
        self.cdp.deposit(value=amount, sender=actor)
        self.collateral[actor] += amount

    @rule(i=actor_st, amount=musd_amount_st)
    def mint(self, i, amount):
        self.steps += 1
        self._try_mint(self.actors[i], amount)

    @rule(i=actor_st, amount=eth_amount_st)
    def open_max_position(self, i, amount):
        """Deposit and mint to the limit in one step: any price drop makes it liquidatable."""
        self.deposit(i, amount)
        self.mint_max(i)

    @rule(i=actor_st)
    def mint_max(self, i):
        actor = self.actors[i]
        self.steps += 1
        amount = max_mintable(self.collateral[actor], self.feed_price) - self._debt(actor)
        # Share rounding can push the exact limit one wei over; step down.
        while amount > 0 and not self._try_mint(actor, amount):
            amount -= 1

    @rule(i=actor_st, amount=musd_amount_st)
    def burn(self, i, amount):
        actor = self.actors[i]
        self.steps += 1
        debt = self._debt(actor)
        if self._partial_repay_below_one_share(amount, debt):
            with boa.reverts(dev="[cdp] repayment below one debt share"):
                self.cdp.burn(amount, sender=actor)
        elif amount <= debt and amount <= self.balance[actor]:
            self.cdp.burn(amount, sender=actor)
            self._accrue()
            removed = self.shares[actor] if amount == debt else amount * PRECISION // self.index
            self.shares[actor] -= removed
            self.balance[actor] -= amount
        else:
            with boa.reverts():
                self.cdp.burn(amount, sender=actor)

    @rule(i=actor_st)
    def repay_all(self, i):
        """Close out the whole debt, buying any missing mUSD from the surplus."""
        actor = self.actors[i]
        self.steps += 1
        debt = self._debt(actor)
        missing = debt - self.balance[actor]
        if missing > 0:
            usd = _ceil_div(missing * PRECISION, PRECISION - SWAP_FEE)
            eth = _ceil_div(usd * PRECISION, self.feed_price * 10**10)
            # Rounding the ETH up buys up to one price unit more than `missing`.
            out = self._bought(eth)
            if out > self._surplus_now() or eth > boa.env.get_balance(actor):
                return
            self._buy_surplus(actor, eth)
        if debt > 0:
            self.cdp.burn(debt, sender=actor)
            self._accrue()
            self.shares[actor] = 0
            self.balance[actor] -= debt

    @rule(i=actor_st, amount=eth_amount_st)
    def withdraw(self, i, amount):
        actor = self.actors[i]
        ok = amount <= self.collateral[actor] and (
            self._ratio(self.collateral[actor] - amount, self._debt(actor))
            >= MIN_COLLAT_RATIO
        )
        if ok:
            self.cdp.withdraw(amount, sender=actor)
            self._accrue()
            self.collateral[actor] -= amount
        else:
            with boa.reverts():
                self.cdp.withdraw(amount, sender=actor)

    @rule(i=actor_st, j=actor_st, amount=musd_amount_st)
    def redeem(self, i, j, amount):
        redeemer, user = self.actors[i], self.actors[j]
        self.steps += 1
        debt, collateral = self._debt(user), self.collateral[user]
        amount = min(amount, self.balance[redeemer])
        if amount == 0:
            with boa.reverts(dev="[cdp_native] amount must be greater than zero (0)."):
                self.cdp.redeem(user, amount, 1, sender=redeemer)
        elif self._ratio(collateral, debt) < MIN_COLLAT_RATIO:
            with boa.reverts(dev="[cdp] position unhealthy"):
                self.cdp.redeem(user, amount, 1, sender=redeemer)
        else:
            ratio = self._ratio(collateral, debt)
            eth = amount * (PRECISION - redemption_fee(ratio)) // (self.feed_price * 10**10)
            if eth == 0:
                with boa.reverts(dev="[cdp] slippage"):
                    self.cdp.redeem(user, amount, 1, sender=redeemer)
                return
            if amount > debt:
                with boa.reverts(dev="[cdp] repay exceeds debt"):
                    self.cdp.redeem(user, amount, 1, sender=redeemer)
                return
            if self._partial_repay_below_one_share(amount, debt):
                with boa.reverts(dev="[cdp] repayment below one debt share"):
                    self.cdp.redeem(user, amount, 1, sender=redeemer)
                return
            redeemer_eth = boa.env.get_balance(redeemer)
            assert self.cdp.redeem(user, amount, 1, sender=redeemer) == eth
            self._accrue()
            assert boa.env.get_balance(redeemer) == redeemer_eth + eth
            removed = self.shares[user] if amount == debt else amount * PRECISION // self.index
            self.shares[user] -= removed
            self.collateral[user] -= eth
            self.balance[redeemer] -= amount
            # Redeeming a healthy position never lowers its ratio.
            assert self._ratio(self.collateral[user], self._debt(user)) >= ratio

    @rule(i=actor_st, j=actor_st, amount=musd_amount_st)
    def transfer(self, i, j, amount):
        sender, to = self.actors[i], self.actors[j]
        amount = min(amount, self.balance[sender])
        self.cdp.transfer(to, amount, sender=sender)
        self.balance[sender] -= amount
        self.balance[to] += amount

    @rule(i=actor_st, eth=st.integers(min_value=0, max_value=10 * ETH))
    def buy_surplus(self, i, eth):
        actor = self.actors[i]
        self.steps += 1
        eth = min(eth, boa.env.get_balance(actor))
        out = self._bought(eth)
        if 0 < out <= self._surplus_now():
            self._buy_surplus(actor, eth)
        else:
            with boa.reverts():
                self.cdp.buy_surplus(value=eth, sender=actor)

    @rule(i=actor_st)
    def buy_out_surplus(self, i):
        """Buy (almost) all of the surplus, so bad debt can outlast it."""
        actor = self.actors[i]
        usd = self._surplus_now() * PRECISION // (PRECISION - SWAP_FEE)
        eth = usd * PRECISION // (self.feed_price * 10**10)
        if 0 < self._bought(eth) and eth <= boa.env.get_balance(actor):
            self.steps += 1
            self._buy_surplus(actor, eth)

    def _buy_surplus(self, actor, eth):
        out = self.cdp.buy_surplus(value=eth, sender=actor)
        self._accrue()
        assert out == self._bought(eth)
        self.surplus -= out
        self.reserve += eth
        self.balance[actor] += out

    @rule(seconds=st.integers(min_value=1, max_value=7 * 86400))
    def warp(self, seconds):
        """Let interest build up, keeping the oracle fresh."""
        boa.env.time_travel(seconds=seconds)
        self._set_price(self.feed_price)

    @rule(feed_price=feed_price_st)
    def set_price(self, feed_price):
        self._set_price(feed_price)

    @rule(drop_bps=st.integers(min_value=1, max_value=5_000))
    def crash_price(self, drop_bps):
        """Drop the price by up to 50%, pushing maxed-out positions underwater."""
        self._set_price(max(self.feed_price * (10_000 - drop_bps) // 10_000, 1))

    def _set_price(self, feed_price):
        self.oracle.set_answer(feed_price)
        self.feed_price = feed_price

    @rule(i=actor_st, j=actor_st, max_repay=max_repay_st)
    def liquidate(self, i, j, max_repay):
        self._try_liquidate(self.actors[i], self.actors[j], max_repay)

    @precondition(lambda self: self._underwater())
    @rule(data=st.data(), max_repay=max_repay_st)
    def keeper_liquidate(self, data, max_repay):
        user = data.draw(st.sampled_from(self._underwater()))
        self._try_liquidate(self.keeper, user, max_repay)

    @rule(j=actor_st)
    def keeper_liquidate_healthy(self, j):
        user = self.actors[j]
        if self._ratio(self.collateral[user], self._debt(user)) >= MIN_COLLAT_RATIO:
            with boa.reverts(dev="[cdp] position healthy"):
                self.cdp.liquidate(user, MAX_UINT256, sender=self.keeper)

    def _try_liquidate(self, liquidator, user, max_repay):
        debt, collateral = self._debt(user), self.collateral[user]
        if max_repay == 0:
            with boa.reverts(dev="[cdp_native] max repay amount must be greater than zero (0)."):
                self.cdp.liquidate(user, max_repay, sender=liquidator)
            return
        if self._ratio(collateral, debt) >= MIN_COLLAT_RATIO:
            with boa.reverts(dev="[cdp] position healthy"):
                self.cdp.liquidate(user, max_repay, sender=liquidator)
            return
        repaid, seized, written_off = liquidation(
            collateral, debt, self.feed_price, max_repay, rate_index=self._index_now()
        )
        if self._closes_position(collateral, debt) and max_repay < repaid:
            with boa.reverts(dev="[cdp] repay too small"):
                self.cdp.liquidate(user, max_repay, sender=liquidator)
        elif written_off == 0 and self._partial_repay_below_one_share(repaid, debt):
            with boa.reverts(dev="[cdp] repayment below one debt share"):
                self.cdp.liquidate(user, max_repay, sender=liquidator)
        elif self.balance[liquidator] < repaid:
            with boa.reverts(dev="[erc20] burn amount exceeds balance"):
                self.cdp.liquidate(user, max_repay, sender=liquidator)
        else:
            self._liquidate(liquidator, user, max_repay, repaid, seized, written_off)

    def _closes_position(self, collateral: int, debt: int) -> bool:
        """True when the collateral covers less than 110% of the debt, so the
        liquidation must repay a fixed amount and take all of it."""
        value = collateral * self.feed_price * 10**10 // PRECISION * PRECISION
        return value < LIQUIDATION_PENALTY * debt

    def _liquidate(self, liquidator, user, max_repay, repaid, seized, written_off):
        self.steps += 1
        debt = self._debt(user)
        liquidator_eth = boa.env.get_balance(liquidator)
        assert self.cdp.liquidate(user, max_repay, sender=liquidator) == repaid
        self._accrue()
        assert boa.env.get_balance(liquidator) == liquidator_eth + seized
        if written_off > 0:
            self.shares[user] = 0
            self.bad_debt += written_off
        elif repaid == debt:
            self.shares[user] = 0
        else:
            self.shares[user] -= repaid * PRECISION // self.index
        self.collateral[user] -= seized
        self.balance[liquidator] -= repaid
        self._settle()
        self.liquidations += 1
        if written_off == 0 and repaid < max_repay:
            # Not capped by the liquidator: the position is healthy again.
            assert self.cdp.collat_ratio(user) >= MIN_COLLAT_RATIO

    @rule(i=actor_st, amount=musd_amount_st)
    def cover_bad_debt(self, i, amount):
        actor = self.actors[i]
        self.steps += 1
        bad_debt = self._after_accrual()[1]
        amount = min(amount, bad_debt, self.balance[actor])
        eth = amount * (PRECISION - SWAP_FEE) // (self.feed_price * 10**10)
        if amount == 0 or eth > self.reserve:
            with boa.reverts():
                self.cdp.cover_bad_debt(amount, sender=actor)
            return
        actor_eth = boa.env.get_balance(actor)
        assert self.cdp.cover_bad_debt(amount, sender=actor) == eth
        self._accrue()
        assert boa.env.get_balance(actor) == actor_eth + eth
        self.bad_debt -= amount
        self.reserve -= eth
        self.balance[actor] -= amount

    # ================= Invariants =================

    @invariant()
    def model_matches_contract(self):
        assert self.cdp.rate_index() == self.index
        assert self.cdp.surplus() == self.surplus
        assert self.cdp.reserve() == self.reserve
        assert self.cdp.bad_debt() == self.bad_debt
        for actor in self.collateral:
            assert self.cdp.collateral(actor) == self.collateral[actor]
            assert self.cdp.debt_shares(actor) == self.shares[actor]
            assert self.cdp.debt(actor) == self._debt(actor)
            assert self.cdp.balanceOf(actor) == self.balance[actor]

    @invariant()
    def supply_backed_by_debt(self):
        """Every mUSD is owed back by a borrower or recorded as bad debt; rounding
        only ever favours the protocol. Debt views include interest not yet minted
        to the surplus, so count it in."""
        supply = self.cdp.totalSupply() + self._pending_fee()
        total_debt = sum(self.cdp.debt(a) for a in self.collateral) + self.bad_debt
        assert supply <= total_debt <= supply + len(self.collateral) + 2 * self.steps
        assert self.cdp.total_debt_shares() == sum(self.shares.values())

    @invariant()
    def eth_held_equals_collateral_plus_reserve(self):
        assert boa.env.get_balance(self.cdp.address) == (
            sum(self.collateral.values()) + self.reserve
        )

    @invariant()
    def no_eth_created_or_destroyed(self):
        held = sum(boa.env.get_balance(a) for a in self.collateral)
        assert (
            held + boa.env.get_balance(self.cdp.address)
            == N_ACTORS * STARTING_ETH + KEEPER_ETH
        )


TestSolvency = SolvencyMachine.TestCase
# FUZZ_EXAMPLES=1000 mox test tests/fuzz for a deeper run (~10 min).
TestSolvency.settings = settings(
    max_examples=int(os.environ.get("FUZZ_EXAMPLES", 100)),
    stateful_step_count=40,
    deadline=None,
)
