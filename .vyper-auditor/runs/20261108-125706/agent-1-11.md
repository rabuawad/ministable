[Feynman: modules/cdp/cdp.vy] The module tracks collateral, debt, interest, liquidations, redemptions, and reserves. Its accounting depends on the wrapper to move collateral.

[Feynman: modules/cdp/cdp_erc20.vy] The wrapper measures collateral received and sends collateral owed. Its accounting assumes an outgoing transfer reduces the contract balance by the requested amount.

[Feynman: modules/cdp/cdp_native.vy] The wrapper receives native coin and sends the amount calculated by the accounting module. Its external calls depend on the recipient accepting the coin.

[Feynman: modules/tokens/erc20.vy] The module tracks stablecoin balances, allowances, and signatures. Its exported functions retain this module’s nonreentrancy setting.

[Socratic: modules/cdp/cdp_erc20.vy:_push — why?] Why does the wrapper measure the balance change for incoming collateral but trust the requested amount for outgoing collateral?

[Inversion: _push] An attacker can withdraw after depositing, select a transfer with a sender fee, or redeem another borrower’s position before other depositors withdraw.

LEAD | contract: modules/cdp/cdp_erc20.vy | function: _push | bug_class: fee-on-transfer-outflow | group_key: modules/cdp/cdp_erc20.vy | _push | fee-on-transfer-outflow
seam: economics×asymmetry
actor: a depositor or redeemer using collateral that charges an additional fee to the sender
code_smells: The wrapper measures incoming collateral but does not measure the collateral that leaves the contract.
proof: If the contract holds 200 tokens for two depositors and an outgoing transfer of 100 deducts 110 from the sender, one withdrawal leaves 90 tokens against the other depositor’s 100-token claim.
unverified: A supported deployment must use a collateral token that charges an additional sender-side fee on outgoing transfers.
description: A depositor can reduce another depositor’s collateral if the token charges the contract an additional sender fee.
