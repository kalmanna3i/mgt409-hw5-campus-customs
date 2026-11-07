# Campus Customs harness

Working database: `data/campus_customs_new.db`. The original `data/campus_customs.db` is never edited. Shop today is `desk.date_today` (2026-08-31 in the original file).

## Tables

### desk
Fields: `date_today`, `notes`.
Why: this date is “today” for overdue bills and rent, so agents do not use the real calendar.

### tickets
Fields: `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at`.
Why: each open job the Boss assigns. 101 links to a tee and invoice 501, 102 links to lease 1, 103 links to a hoodie qty.

### inventory
Fields: `sku`, `name`, `size`, `qty`, `location`. Primary key `(sku, size)`.
Why: Inventory has to see that CC-TEE-WHITE / S is 0 and CC-HOOD-NAVY / M is 8 before anyone promises a shirt.

### pricing
Fields: `sku`, `unit_cost`, `list_price`.
Why: Accounting needs the $22 cost and $58 list on the navy hoodie before it quotes a bulk discount.

### vendors
Fields: `id`, `name`, `specialty`, `lead_days`.
Why: lead time and who reprints apparel (Bulldog Print Co, 5 days) versus mugs (Elm City Gifts).

### leases
Fields: `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`.
Why: Facilities uses lease 1, Chapel Street shop, $2400 due 2026-09-02, for the rent ticket.

### cash_accounts
Fields: `name`, `balance`, `date`.
Why: checking starts at $3400. Payments have to fit in that balance.

### payments
Fields: `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`.
Why: the record that a human actually approved money leaving the shop.

### invoices
Fields: `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`.
Why: invoice 501 is the $840 overdue reprint for the white tee. While it is open, that vendor will not ship.

## MCP tools added first (Problem 3)

### get_ticket
Table: `tickets`. Ticket 101. The row is the only place that says the order is one CC-TEE-WHITE in size S and that invoice 501 is attached, so the rest of the team knows which bill is blocking the shirt.

### check_inventory
Table: `inventory`. Ticket 103. Yale AI Club asked for 20 navy hoodies in size M, and this tool is the one that shows only 8 are in Aisle A, so the quote cannot pretend 20 are on the shelf. The same tool is what shows ticket 101’s size S tee at qty 0.

### get_invoice
Table: `invoices`. Ticket 101. Invoice 501 is $840, due 2026-08-28, status open. That is the overdue Bulldog Print Co bill, and the vendor will not ship the reprint until it is paid.

## MCP tools added for the agent team

### get_lease
Table: `leases`. Ticket 102. Facilities needs the Chapel Street rent amount and the 2026-09-02 due date, which is two days after shop today.

### list_vendors
Table: `vendors`. Every ticket that needs a lead time. Lead days are read here, not guessed.

### vendor_for_sku
Table: `vendors`. Tickets 101 and 103. Apparel skus map to Bulldog Print Co.

### vendor_open_invoices
Table: `invoices`. Tickets 101 and 103. An open row means that vendor will not ship.

### get_pricing
Table: `pricing`. Ticket 103. Accounting uses unit cost $22 and list $58 to keep a 15% quote above cost.

### get_cash_account
Table: `cash_accounts`. Tickets 101, 102, and 103. This is the check that refuses a payment when checking would go negative.

### get_desk
Table: `desk`. Tickets 101 and 102. Overdue and “due in 2 days” are computed from `date_today`.

### list_tickets
Table: `tickets`. The desk board. Returns all three tickets and whether each is open or resolved.

### prepare_payment_request
Table: `cash_accounts` (read only). Tickets 101 and 102. Accounting uses it to prepare a pay without moving cash.

### apply_approved_payment
Tables: `payments`, `cash_accounts`, and then `invoices` or `leases` or `inventory`. Tickets 101 and 102. This is the only tool that changes cash, and only after a human name is supplied.

### set_ticket_status
Table: `tickets`. All three tickets. Writes `resolved` and the outcome note when the work is actually done.

## Agents

- Boss — reads the ticket and calls one specialist first. Does not pay.
- Inventory — stock, shortfall, vendor, lead time, unpaid-invoice block.
- Accounting — cash, overdue bills, rent math, discount above cost, prepares payments.
- Facilities — lease and rent only.
- Customer Service — drafts a board message and does not send it.

Every agent is a PydanticAI agent on `gpt-6-luna` through Portkey (`PORTKEY_API_KEY`). Shop numbers come from the MCP tools above.

## API routes

- `GET /tickets` — three tickets plus open/resolved and any pay waiting for a human.
- `POST /tickets/{ticket_id}/run` — Boss runs the team on that ticket.
- `GET /events` — recent agent lines and tool names for the board.
- `POST /approve-pay` — a human approves the prepared pay. This is the call that changes cash.
- `GET /cash` — current checking balance from `cash_accounts`.
- `POST /reset` — copies the original database over the working copy and clears the board log. It does not delete `audit_trail.json`.

## Dashboard

The React desk lists tickets 101, 102, and 103, runs the team on the one you pick, shows each agent’s lines, stamps a ticket resolved, asks a named human to approve a pay, and shows the checking balance dropping after that approval.

## Safety and token limits

- A human name is required before cash moves. Agents can only prepare a payment.
- `apply_approved_payment` refuses a negative checking balance, a mismatched amount, or a second pay of the same invoice or rent.
- No email is sent and no vendor is called. Drafts stay on the board.
- Agents may use only MCP tool results for shop facts.
- Each model reply is capped at 1200 tokens. A run stops after 8 agent steps. If `gpt-6-luna` does not answer, the desk keeps the shop-rule sentence already produced from the tool output instead of calling another model.
