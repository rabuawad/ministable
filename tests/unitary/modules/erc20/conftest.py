import boa
import pytest

from tests.utils.constants import ETH
from tests.utils.helpers import deploy_erc20

# Balance the `holder` fixture starts with.
HOLDER_BALANCE = 1000 * ETH


@pytest.fixture(scope="module")
def musd(admin):
    """The `erc20` module alone: no CDP engine, `mint`/`burn` exposed."""
    with boa.env.prank(admin):
        return deploy_erc20()


@pytest.fixture
def holder(musd, borrower):
    musd.mint(borrower, HOLDER_BALANCE)
    return borrower
