import boa
import pytest
from eth_abi import encode
from eth_account import Account
from eth_utils import keccak

from tests.utils.constants import ETH
from tests.utils.permit import sign_permit


@pytest.fixture(scope="module")
def signer():
    return Account.create()


EIP712_DOMAIN_TYPE_HASH = keccak(
    text="EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)


def _deadline():
    return boa.env.evm.patch.timestamp + 3600


def test_permit_sets_allowance(musd, signer, recipient):
    deadline = _deadline()
    v, r, s = sign_permit(musd, signer, recipient, 100 * ETH, deadline)

    musd.permit(
        signer.address, recipient, 100 * ETH, deadline, v, r, s, sender=recipient
    )

    assert musd.allowance(signer.address, recipient) == 100 * ETH
    assert musd.nonces(signer.address) == 1


def test_permit_replay_reverts(musd, signer, recipient):
    deadline = _deadline()
    v, r, s = sign_permit(musd, signer, recipient, 100 * ETH, deadline)
    musd.permit(signer.address, recipient, 100 * ETH, deadline, v, r, s)

    with boa.reverts(dev="[erc20] invalid signature"):
        musd.permit(signer.address, recipient, 100 * ETH, deadline, v, r, s)


def test_permit_wrong_value_reverts(musd, signer, recipient):
    deadline = _deadline()
    v, r, s = sign_permit(musd, signer, recipient, 100 * ETH, deadline)

    with boa.reverts(dev="[erc20] invalid signature"):
        musd.permit(signer.address, recipient, 101 * ETH, deadline, v, r, s)


def test_permit_expired_deadline_reverts(musd, signer, recipient):
    deadline = _deadline()
    v, r, s = sign_permit(musd, signer, recipient, 100 * ETH, deadline)
    boa.env.time_travel(seconds=3601)

    with boa.reverts(dev="[erc20] expired deadline"):
        musd.permit(signer.address, recipient, 100 * ETH, deadline, v, r, s)


def test_domain_separator(musd):
    """Matches the EIP-712 hash built off-chain from `eip712Domain()`."""
    _, name, version, chain_id, verifying_contract, _, _ = musd.eip712Domain()
    expected = keccak(
        encode(
            ["bytes32", "bytes32", "bytes32", "uint256", "address"],
            [
                EIP712_DOMAIN_TYPE_HASH,
                keccak(text=name),
                keccak(text=version),
                chain_id,
                verifying_contract,
            ],
        )
    )

    assert musd.DOMAIN_SEPARATOR() == expected
