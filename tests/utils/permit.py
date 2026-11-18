from eth_account import Account

PERMIT_TYPES = {
    "Permit": [
        {"name": "owner", "type": "address"},
        {"name": "spender", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ]
}


def sign_permit(musd, signer, spender, value, deadline, nonce=None):
    _, name, version, chain_id, verifying_contract, _, _ = musd.eip712Domain()
    domain = {
        "name": name,
        "version": version,
        "chainId": chain_id,
        "verifyingContract": verifying_contract,
    }
    message = {
        "owner": signer.address,
        "spender": spender,
        "value": value,
        "nonce": musd.nonces(signer.address) if nonce is None else nonce,
        "deadline": deadline,
    }
    signed = Account.sign_typed_data(signer.key, domain, PERMIT_TYPES, message)
    return signed.v, signed.r.to_bytes(32, "big"), signed.s.to_bytes(32, "big")
