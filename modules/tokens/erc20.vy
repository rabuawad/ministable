# pragma version ~=0.4.3
# pragma nonreentrancy off
"""
@title Modern and Gas-Efficient ERC-20 + EIP-2612 Implementation
@custom:contract-name erc20
@license GNU Affero General Public License v3.0 only
@author rafael-abuawad
"""


# @dev We import and implement the `IERC20` interface,
# which is a built-in interface of the Vyper compiler.
from ethereum.ercs import IERC20
implements: IERC20


# @dev We import and implement the `IERC20Detailed` interface,
# which is a built-in interface of the Vyper compiler.
from ethereum.ercs import IERC20Detailed
implements: IERC20Detailed


# @dev We import and implement the `IERC20Permit`
# interface, which is written using standard Vyper
# syntax.
from snekmate.tokens.interfaces import IERC20Permit
implements: IERC20Permit


# @dev We import and implement the `IERC5267` interface,
# which is written using standard Vyper syntax.
from snekmate.utils.interfaces import IERC5267
implements: IERC5267


# @dev We import and use the `ownable` module.
from snekmate.auth import ownable
uses: ownable


# @dev We import the `ecdsa` module.
# @notice Please note that the `ecdsa` module
# is stateless and therefore does not require
# the `uses` keyword for usage.
from snekmate.utils import ecdsa


# @dev We import and initialise the `eip712_domain_separator` module.
from snekmate.utils import eip712_domain_separator
initializes: eip712_domain_separator


# @dev We export (i.e. the runtime bytecode exposes these
# functions externally, allowing them to be called using
# the ABI encoding specification) the `external` getter
# function `owner` from the `ownable` module as well as the
# function `eip712Domain` from the `eip712_domain_separator`
# module.
# @notice Please note that you must always also export (if
# required by the contract logic) `public` declared `constant`,
# `immutable`, and state variables, for which Vyper automatically
# generates an `external` getter function for the variable.
exports: (
    # @notice This ERC-20 implementation includes the `transfer_ownership`
    # and `renounce_ownership` functions, which incorporate
    # the additional built-in `is_minter` role logic and are
    # therefore not exported from the `ownable` module.
    ownable.owner,
    eip712_domain_separator.eip712Domain,
)


# @dev The 32-byte type hash of the `permit` function.
_PERMIT_TYPE_HASH: constant(bytes32) = keccak256(
    "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
)


# @dev Returns the name of the token.
# @notice If you declare a variable as `public`,
# Vyper automatically generates an `external`
# getter function for the variable. Furthermore,
# to preserve consistency with the interface for
# the optional metadata functions of the ERC-20
# standard, we use lower case letters for the
# `immutable` variables `name`, `symbol`, and
# `decimals`.
name: public(immutable(String[25]))


# @dev Returns the symbol of the token.
# @notice See comment on lower case letters
# above at `name`.
symbol: public(immutable(String[15]))


# @dev Returns the decimal places of the token.
# @notice See comment on lower case letters
# above at `name`.
decimals: public(immutable(uint8))


# @dev Returns the amount of tokens owned by an `address`.
balanceOf: public(HashMap[address, uint256])


# @dev Returns the remaining number of tokens that a
# `spender` will be allowed to spend on behalf of
# `owner` through `transferFrom`. This is zero by
# default. This value changes when `approve` or
# `transferFrom` are called.
allowance: public(HashMap[address, HashMap[address, uint256]])


# @dev Returns the amount of tokens in existence.
totalSupply: public(uint256)


# @dev Returns the current on-chain tracked nonce
# of `address`.
nonces: public(HashMap[address, uint256])


@deploy
@payable
def __init__(
    name_: String[25],
    symbol_: String[15],
    decimals_: uint8,
    name_eip712_: String[50],
    version_eip712_: String[20],
):
    name = name_
    symbol = symbol_
    decimals = decimals_
    eip712_domain_separator.__init__(name_eip712_, version_eip712_)


@external
def transfer(to: address, amount: uint256) -> bool:
    self._transfer(msg.sender, to, amount)
    return True


@external
def approve(spender: address, amount: uint256) -> bool:
    self._approve(msg.sender, spender, amount)
    return True


@external
def transferFrom(owner: address, to: address, amount: uint256) -> bool:
    self._spend_allowance(owner, msg.sender, amount)
    self._transfer(owner, to, amount)
    return True




@external
def permit(owner: address, spender: address, amount: uint256, deadline: uint256, v: uint8, r: bytes32, s: bytes32):
    assert block.timestamp <= deadline # dev: [erc20] expired deadline

    current_nonce: uint256 = self.nonces[owner]
    self.nonces[owner] = unsafe_add(current_nonce, 1)

    struct_hash: bytes32 = keccak256(abi_encode(_PERMIT_TYPE_HASH, owner, spender, amount, current_nonce, deadline))
    hash: bytes32 = eip712_domain_separator._hash_typed_data_v4(struct_hash)

    signer: address = ecdsa._recover_vrs(hash, convert(v, uint256), convert(r, uint256), convert(s, uint256))
    assert signer == owner # dev: [erc20] invalid signature

    self._approve(owner, spender, amount)


@external
@view
def DOMAIN_SEPARATOR() -> bytes32:
    return eip712_domain_separator._domain_separator_v4()


@internal
def _transfer(owner: address, to: address, amount: uint256):
    assert owner != empty(address) # dev: [erc20] transfer from the zero address
    assert to != empty(address) # dev: [erc20] transfer to the zero address

    self._before_token_transfer(owner, to, amount)

    owner_balanceOf: uint256 = self.balanceOf[owner]
    assert owner_balanceOf >= amount # dev: [erc20] transfer amount exceeds balance
    self.balanceOf[owner] = unsafe_sub(owner_balanceOf, amount)
    self.balanceOf[to] = unsafe_add(self.balanceOf[to], amount)
    log IERC20.Transfer(sender=owner, receiver=to, value=amount)

    self._after_token_transfer(owner, to, amount)


@internal
def _mint(owner: address, amount: uint256):
    assert owner != empty(address) # dev: [erc20] mint to the zero address

    self._before_token_transfer(empty(address), owner, amount)

    self.totalSupply += amount
    self.balanceOf[owner] = unsafe_add(self.balanceOf[owner], amount)
    log IERC20.Transfer(sender=empty(address), receiver=owner, value=amount)

    self._after_token_transfer(empty(address), owner, amount)


@internal
def _burn(owner: address, amount: uint256):
    assert owner != empty(address) # dev: [erc20] burn from the zero address

    self._before_token_transfer(owner, empty(address), amount)

    account_balance: uint256 = self.balanceOf[owner]
    assert account_balance >= amount # dev: [erc20] burn amount exceeds balance
    self.balanceOf[owner] = unsafe_sub(account_balance, amount)
    self.totalSupply = unsafe_sub(self.totalSupply, amount)
    log IERC20.Transfer(sender=owner, receiver=empty(address), value=amount)

    self._after_token_transfer(owner, empty(address), amount)


@internal
def _approve(owner: address, spender: address, amount: uint256):
    assert owner != empty(address) # dev: [erc20] approve from the zero address
    assert spender != empty(address) # dev: [erc20] approve to the zero address

    self.allowance[owner][spender] = amount
    log IERC20.Approval(owner=owner, spender=spender, value=amount)


@internal
def _spend_allowance(owner: address, spender: address, amount: uint256):
    current_allowance: uint256 = self.allowance[owner][spender]
    if current_allowance < max_value(uint256):
        assert current_allowance >= amount # dev: [erc20] insufficient allowance
        self._approve(owner, spender, unsafe_sub(current_allowance, amount))


@internal
def _before_token_transfer(owner: address, to: address, amount: uint256):
    """
    @dev Hook that is called before any transfer of tokens.
         This includes minting and burning.
    @notice The calling conditions are:
            - when `owner` and `to` are both non-zero,
              `amount` of `owner`'s tokens will be
              transferred to `to`,
            - when `owner` is zero, `amount` tokens will
              be minted for `to`,
            - when `to` is zero, `amount` of `owner`'s
              tokens will be burned,
            - `owner` and `to` are never both zero.
    @param owner The 20-byte owner address.
    @param to The 20-byte receiver address.
    @param amount The 32-byte token amount to be transferred.
    """
    pass


@internal
def _after_token_transfer(owner: address, to: address, amount: uint256):
    """
    @dev Hook that is called after any transfer of tokens.
         This includes minting and burning.
    @notice The calling conditions are:
            - when `owner` and `to` are both non-zero,
              `amount` of `owner`'s tokens has been
              transferred to `to`,
            - when `owner` is zero, `amount` tokens
              have been minted for `to`,
            - when `to` is zero, `amount` of `owner`'s
              tokens have been burned,
            - `owner` and `to` are never both zero.
    @param owner The 20-byte owner address.
    @param to The 20-byte receiver address.
    @param amount The 32-byte token amount that has
           been transferred.
    """
    pass
