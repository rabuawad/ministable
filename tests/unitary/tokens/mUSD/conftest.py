import boa
import pytest

from tests.utils.helpers import deploy_stable


@pytest.fixture(scope="module")
def stable(oracle, admin):
    with boa.env.prank(admin):
        return deploy_stable(oracle.address)
