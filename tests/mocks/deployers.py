from pathlib import Path

import boa

MOCKS_DIR = Path(__file__).parent

MOCK_AGGREGATOR = boa.load_partial(str(MOCKS_DIR / "mock_aggregator.vy"))
MOCK_RECEIVER = boa.load_partial(str(MOCKS_DIR / "mock_receiver.vy"))
MOCK_TOKEN = boa.load_partial(str(MOCKS_DIR / "mock_token.vy"))
MOCK_TOKEN_NO_RETURN = boa.load_partial(str(MOCKS_DIR / "mock_token_no_return.vy"))
CDP_ERC20_HARNESS = boa.load_partial(str(MOCKS_DIR / "cdp_erc20_harness.vy"))
CDP_NATIVE_HARNESS = boa.load_partial(str(MOCKS_DIR / "cdp_native_harness.vy"))
ERC20_HARNESS = boa.load_partial(str(MOCKS_DIR / "erc20_harness.vy"))
MOCK_REENTRANT_CALLER = boa.load_partial(str(MOCKS_DIR / "mock_reentrant_caller.vy"))
