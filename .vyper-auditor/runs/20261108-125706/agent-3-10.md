[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt shares, interest, and payouts; its first numerical assumption is that rounded share changes match token payments.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens; its first token assumption is that the contract loses exactly the requested output amount.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin; its first accounting assumption is that each payout matches the debt change.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances and permits; its first arithmetic assumption is that supply bounds make its unsafe balance operations valid.

[Socratic: modules/cdp/cdp.vy:_repay — why?] Why does a positive payment permit zero shares to be removed?

[Inversion: _repay] A caller can choose a one-unit payment, target a high `rate_index`, or repeat payments against another user’s position through redemption.

[Inversion: _push] A caller can withdraw a large balance, use a token that charges the sender, or redeem through a token that charges the recipient.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
seam: precision×invariant
path: depositor → withdraw → accounting removes the requested amount → sender-fee token removes more from the contract → other depositors lose collateral
proof: Alice and Bob each have 100 credited units, and the contract holds 200 units. If the token charges the sender 10%, Alice’s withdrawal of 100 reduces her credit by 100 but reduces the contract balance by 110. Bob retains a claim of 100 against the remaining 90. `_push` asserts the transfer result but does not measure the contract’s balance decrease.
description: A depositor can withdraw with a sender-fee token and consume collateral owed to other depositors.
fix: The module should reject a transfer if the contract balance decreases by more than the amount deducted from accounting.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
seam: boundary×invariant
path: redeemer → redeem with `min_paid` → gross payout passes the check → recipient-fee token pays less → redeemer receives less than the minimum
proof: If `_redeem` calculates `paid = 100` and `min_paid = 100`, the check passes. A token that deducts a 10% recipient fee delivers 90, while `redeem` returns 100.
description: A redeemer can receive less collateral than `min_paid` when the token charges a recipient fee.
fix: The module should check the recipient’s balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _redeem | bug_class: zero-share-redemption | group_key: modules/cdp/cdp.vy | _redeem | zero-share-redemption
seam: three-way
code_smells: The function pays collateral after `_repay` rounds a positive payment down to zero shares.
unverified: A materially harmful execution requires a reachable `rate_index` and collateral price that make repeated payouts exceed transaction costs.
proof: At `rate_index = 3e18`, debt shares of 4 imply debt of 12 units. With `p = 1e18` and collateral of 18 units, redemption of 2 units pays 1 collateral unit but removes `2 * 1e18 // 3e18 = 0` shares. The ratio falls from 150% to `17 / 12`, below 150%.
description: A redeemer can remove collateral without reducing the borrower’s debt when share removal rounds to zero.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: zero-share-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | zero-share-liquidation
seam: three-way
code_smells: The function permits a positive `repay` that removes zero debt shares.
unverified: A materially harmful execution requires a reachable `rate_index`, collateral price, and transaction cost that make repeated payouts economical.
proof: At `rate_index = 3e18`, `max_repay = 2` removes `2 * 1e18 // 3e18 = 0` shares. With `p = 1e18`, the liquidator receives `2 * 1.1e18 // 1e18 = 2` collateral units while the debt stays unchanged.
description: A liquidator can remove collateral without reducing the borrower’s debt when share removal rounds to zero.
