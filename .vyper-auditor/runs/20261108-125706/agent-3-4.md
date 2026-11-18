[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, and liquidations. Its accounting assumes each wrapper transfers the collateral amount it records.

[Feynman: modules/cdp/cdp_erc20.vy] The module receives and sends collateral tokens. Its balance checks assume outgoing transfers debit only the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The module receives and sends native coin. Its calls assume the recipient accepts the payment.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances and approvals. Its exported functions keep their own nonreentrancy setting.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the module measure received collateral but assume the token debits and credits exactly `amount` on an outgoing transfer?

[Inversion: _push] An attacker withdraws with a sender-fee token; a redeemer receives less with a recipient-fee token; a token rejects a zero transfer.

[Inversion: _liquidate] A caller supplies a small `max_repay`; a position falls below 100% collateralization; a token rejects the resulting zero payout.

[Inversion: _buy_surplus] A buyer supplies a fixed payment; the oracle updates before execution; the surplus contains less than the requested output.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
path: borrower → withdraw → `_withdraw` reduces recorded collateral → `_push` debits extra collateral → other borrowers lose backing
input: The borrower withdraws 100 units of a collateral token that charges the sender an additional 10 units.
assumption: The token debits the contract by exactly the requested transfer amount.
proof: Two borrowers each deposit 100 units, so the contract holds 200 and records 200. One borrower withdraws 100; `_withdraw` removes 100 from that borrower, while `_push` transfers 100 and the token debits 110. The contract holds 90 against the other borrower’s recorded 100.
description: A borrower can withdraw with a sender-fee token and consume collateral that belongs to other borrowers.
fix: The module must reject an outgoing transfer unless its balance decreases by exactly the recorded amount.

FINDING | contract: modules/cdp/cdp_erc20.vy | function: redeem | bug_class: redemption-net-output-slippage | group_key: modules/cdp/cdp_erc20.vy | redeem | redemption-net-output-slippage
path: redeemer → redeem → `_redeem` checks nominal `paid` → `_push` transfers collateral → redeemer receives less than `min_paid`
input: The redeemer sets `min_paid` to 100 units, and the collateral token charges a 10-unit recipient fee.
assumption: The recipient receives the nominal transfer amount.
proof: `_redeem` accepts `paid = 100` when `min_paid = 100`; `_push(msg.sender, 100)` then returns successfully even if the token credits the redeemer only 90 units.
description: A redeemer can receive less collateral than `min_paid` when the collateral token charges a recipient fee.
fix: The module must check the recipient’s balance increase against `min_paid` after the transfer.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: all-or-nothing-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | all-or-nothing-liquidation
code_smells: The function requires `max_repay >= repay` and removes all debt shares when collateral value is below 110% of debt.
unverified: The available stablecoin liquidity and transaction mechanisms must be checked for a position whose full repayment exceeds one caller’s available balance.
description: A large underwater position can require more stablecoin than one liquidator can obtain.

LEAD | contract: modules/cdp/cdp.vy | function: _liquidate | bug_class: zero-share-liquidation | group_key: modules/cdp/cdp.vy | _liquidate | zero-share-liquidation
code_smells: The function accepts a positive partial `repay` even when `_repay` calculates zero shares to remove.
unverified: The reachable interest index, collateral price, and transaction costs must permit a material payout from repeated calls.
description: A liquidator can pay a small amount while the borrower keeps all debt shares.

LEAD | contract: modules/cdp/cdp.vy | function: _buy_surplus | bug_class: missing-purchase-slippage | group_key: modules/cdp/cdp.vy | _buy_surplus | missing-purchase-slippage
code_smells: The function calculates `bought` from the execution-time oracle price and accepts no minimum output.
unverified: The buyer’s transaction flow and oracle updates must permit a material change between the buyer’s quote and execution.
description: A buyer can receive fewer stablecoins than expected after an oracle update.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: liquidate | bug_class: zero-amount-transfer-revert | group_key: modules/cdp/cdp_erc20.vy | liquidate | zero-amount-transfer-revert
code_smells: The function calls `_push` even when `_liquidate` returns zero collateral.
unverified: A supported collateral token must reject zero transfers, and the reachable liquidation state must require a zero payout.
description: A collateral token that rejects zero transfers can make a liquidation fail.
