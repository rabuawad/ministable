import boa
import pytest

from tests.mocks.deployers import MOCK_AGGREGATOR, MOCK_RECEIVER
from tests.utils.constants import (
    ETH,
    ETH_USD_PRICE,
    ORACLE_DECIMALS,
    POSITION_COLLATERAL,
    POSITION_DEBT,
)
from tests.utils.helpers import deploy_cdp_native

boa.env.enable_fast_mode()

ACCOUNT_BALANCE = 100 * ETH


def _funded_account(name: str) -> str:
    account = boa.env.generate_address(name)
    boa.env.set_balance(account, ACCOUNT_BALANCE)
    return account


# ================= Accounts =================


@pytest.fixture(scope="module")
def admin():
    return boa.env.eoa


@pytest.fixture(scope="module")
def borrower():
    return _funded_account("borrower")


@pytest.fixture(scope="module")
def liquidator():
    return _funded_account("liquidator")


@pytest.fixture(scope="module")
def recipient():
    return _funded_account("recipient")


# ================= Contracts =================


@pytest.fixture(scope="module")
def oracle():
    return MOCK_AGGREGATOR.deploy(ETH_USD_PRICE, ORACLE_DECIMALS)


# `cdp` is the `cdp_native` harness by default; `tests/unitary/modules/cdp_erc20`
# overrides it (and the position fixtures) with the `cdp_erc20` harness.
@pytest.fixture(scope="module")
def cdp(oracle, admin):
    with boa.env.prank(admin):
        return deploy_cdp_native(oracle.address)


@pytest.fixture(scope="module")
def receiver(cdp):
    contract = MOCK_RECEIVER.deploy(cdp.address)
    boa.env.set_balance(contract.address, ACCOUNT_BALANCE)
    return contract


# ================= Positions =================
# Function-scoped: module-scoped state would leak into every later test
# in the module that shares the same accounts.


@pytest.fixture
def borrower_position(cdp, borrower):
    """1 ETH collateral, 1000 mUSD debt -> 200% at $2000."""
    cdp.deposit(value=POSITION_COLLATERAL, sender=borrower)
    cdp.mint(POSITION_DEBT, sender=borrower)
    return borrower


@pytest.fixture
def funded_liquidator(cdp, liquidator):
    """Liquidator holding enough mUSD to repay the borrower's debt."""
    cdp.deposit(value=10 * ETH, sender=liquidator)
    cdp.mint(POSITION_DEBT, sender=liquidator)
    return liquidator
