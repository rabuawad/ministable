# pragma version ~=0.4.3
"""
@title Mock re-entrant caller
@notice Forwards arbitrary calldata to `TARGET`. When it receives
        the native coin, it calls `TARGET` again with `reenter_data`,
        so any function that pays out ETH can be probed for
        re-entrancy. With empty `reenter_data` it accepts ETH quietly.
"""


TARGET: public(immutable(address))


reenter_data: public(Bytes[256])


@deploy
def __init__(target: address):
    TARGET = target


@external
def set_reenter_data(data: Bytes[256]):
    self.reenter_data = data


@payable
@external
def forward(data: Bytes[256]) -> Bytes[256]:
    return raw_call(TARGET, data, value=msg.value, max_outsize=256)


@payable
@external
def __default__():
    if len(self.reenter_data) > 0:
        raw_call(TARGET, self.reenter_data)
