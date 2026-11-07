# Campus Customs MCP server

This server is the only door to the shop database. Agents and the FastAPI desk call these tools instead of inventing stock, prices, or cash.

Database: `data/campus_customs_new.db` (the working copy). Leave `data/campus_customs.db` untouched so the desk can reset.

Tools:

- `get_ticket` reads `tickets`
- `check_inventory` reads `inventory`
- `get_invoice` reads `invoices`
- `get_lease` reads `leases`
- `list_vendors` reads `vendors`
- `vendor_for_sku` reads `vendors`
- `vendor_open_invoices` reads `invoices`
- `get_pricing` reads `pricing`
- `get_cash_account` reads `cash_accounts`
- `get_desk` reads `desk`
- `list_tickets` reads `tickets`
- `prepare_payment_request` reads `cash_accounts` and does not move money
- `apply_approved_payment` writes `payments` and `cash_accounts`, and updates `invoices`, `leases`, or `inventory` after a human approves
- `set_ticket_status` writes `tickets`

Start it from the project root with `python3 mcp_server/server.py`. Cursor loads that command from `.mcp.json`.
