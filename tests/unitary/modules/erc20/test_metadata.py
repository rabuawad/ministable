from tests.utils.helpers import deploy_erc20


def test_token_metadata(musd):
    assert musd.name() == "ministable"
    assert musd.symbol() == "mUSD"
    assert musd.decimals() == 18


def test_custom_metadata():
    token = deploy_erc20("Other Dollar", "oUSD", 6, "Other", "2")

    assert (token.name(), token.symbol(), token.decimals()) == ("Other Dollar", "oUSD", 6)
    _, name, version, _, _, _, _ = token.eip712Domain()
    assert (name, version) == ("Other", "2")


def test_initial_supply_is_zero(musd):
    assert musd.totalSupply() == 0


def test_deployer_is_owner(musd, admin):
    assert musd.owner() == admin


def test_eip712_domain(musd):
    _, name, version, _, verifying_contract, _, _ = musd.eip712Domain()
    assert name == "ministable"
    assert version == "1"
    assert verifying_contract == musd.address
