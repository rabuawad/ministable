import boa
import pytest

from tests.mocks.deployers import MOCK_TOKEN
from tests.utils.constants import ETH, POSITION_COLLATERAL, POSITION_DEBT
from tests.utils.helpers import deploy_cdp_erc20, fund

# ================= Contracts =================
# The default collateral is an 18-decimal token priced like ETH ($2000 on
# the 8-decimal feed), so the `cdp_native` constants and helpers carry over.


@pytest.fixture(scope="module")
def token():
    return MOCK_TOKEN.deploy(18)


@pytest.fixture(scope="module")
def cdp(token, oracle, admin):
    with boa.env.prank(admin):
        return deploy_cdp_erc20(token.address, oracle.address)


# ================= Positions =================


@pytest.fixture
def funded_borrower(cdp, token, borrower):
    fund(token, cdp, borrower)
    return borrower


@pytest.fixture
def borrower_position(cdp, funded_borrower):
    """1 token collateral, 1000 mUSD debt -> 200% at $2000."""
    cdp.deposit(POSITION_COLLATERAL, sender=funded_borrower)
    cdp.mint(POSITION_DEBT, sender=funded_borrower)
    return funded_borrower


@pytest.fixture
def funded_liquidator(cdp, token, liquidator):
    """Liquidator holding enough mUSD to repay the borrower's debt."""
    fund(token, cdp, liquidator)
    cdp.deposit(10 * ETH, sender=liquidator)
    cdp.mint(POSITION_DEBT, sender=liquidator)
    return liquidator
