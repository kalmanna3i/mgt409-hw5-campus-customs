"""Boss-led runs for tickets 101, 102, and 103.

Each specialist is called only when that ticket needs them. Payments wait for a human.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import state
from backend.agents import speak
from mcp_server import tools

MAX_STEPS = 8


class StepCap(Exception):
    pass


def _say(count: list[int], ticket_id: int, agent: str, fallback: str, tool: str | None = None, tool_input=None, tool_output=None) -> None:
    if count[0] >= MAX_STEPS:
        raise StepCap(agent)
    count[0] += 1
    text = speak(agent, str(tool_output), fallback)
    state.append_step(ticket_id, agent, text, tool, tool_input, tool_output)


def run_ticket(ticket_id: int) -> dict:
    ticket = tools.get_ticket(ticket_id)
    if "error" in ticket:
        return {"ok": False, "ticket_id": ticket_id, "status": "missing", "summary": {}, "error": ticket["error"]}
    if ticket["status"] == "resolved":
        return {"ok": False, "ticket_id": ticket_id, "status": "resolved", "summary": state.summaries_for(ticket_id), "error": "ticket is already resolved"}
    if state.get_pending(ticket_id):
        return {"ok": False, "ticket_id": ticket_id, "status": "awaiting_approval", "summary": state.summaries_for(ticket_id), "error": "already waiting for a human to approve a payment"}

    desk = tools.get_desk()
    count = [0]
    try:
        if ticket["type"] == "customer_order":
            return _customer_order(ticket, desk, count)
        if ticket["type"] == "rent_notice":
            return _rent(ticket, desk, count)
        if ticket["type"] == "price_override":
            return _price(ticket, desk, count)
    except StepCap:
        return {"ok": False, "ticket_id": ticket_id, "status": ticket["status"], "summary": state.summaries_for(ticket_id), "error": "stopped: agent step limit reached"}
    return {"ok": False, "ticket_id": ticket_id, "status": ticket["status"], "summary": {}, "error": f"unknown ticket type {ticket['type']}"}


def _customer_order(ticket: dict, desk: dict, count: list[int]) -> dict:
    ticket_id = ticket["id"]
    _say(
        count,
        ticket_id,
        "boss",
        f"Ticket {ticket_id} is a customer order from {ticket['requester']} for {ticket['qty']} {ticket['sku']} size {ticket['size']}. I am calling Inventory first to see if that size is on the shelf. I am not calling Facilities.",
    )
    stock = tools.check_inventory(ticket["sku"], ticket["size"])
    _say(
        count,
        ticket_id,
        "inventory",
        f"{stock.get('name', ticket['sku'])} size {ticket['size']} has qty {stock.get('qty')} in {stock.get('location')}. The order needs {ticket['qty']}.",
        "check_inventory",
        {"sku": ticket["sku"], "size": ticket["size"]},
        stock,
    )
    if "error" in stock:
        return _finish_open(ticket_id, count, "Inventory could not find that sku and size, so I am leaving the ticket open.")

    if int(stock["qty"]) >= int(ticket["qty"]):
        note = f"Filled from stock on hand. Qty left was not reduced because this homework does not record a sale."
        tools.set_ticket_status(ticket_id, "resolved", note)
        _say(count, ticket_id, "boss", f"Size is in stock. Ticket {ticket_id} is resolved without a payment. {note}")
        return _ok(ticket_id, "resolved")

    vendor = tools.vendor_for_sku(ticket["sku"])
    bills = tools.vendor_open_invoices(vendor["id"]) if "error" not in vendor else []
    _say(
        count,
        ticket_id,
        "inventory",
        f"Short by {int(ticket['qty']) - int(stock['qty'])}. {vendor.get('name')} handles this sku, lead time {vendor.get('lead_days')} days. Open unpaid invoices for that vendor: {len(bills)}. They will not ship while a bill is open. Accounting should look at invoice {ticket.get('invoice_id')}.",
        "vendor_for_sku",
        {"sku": ticket["sku"]},
        {"vendor": vendor, "open_invoices": bills},
    )
    invoice = tools.get_invoice(int(ticket["invoice_id"])) if ticket.get("invoice_id") else {"error": "ticket has no invoice"}
    today = desk["date_today"]
    overdue = "error" not in invoice and str(invoice["due_date"]) < today
    prep = tools.prepare_payment_request(invoice["amount"]) if "error" not in invoice else {"allowed": False, "reason": invoice.get("error")}
    if overdue and invoice.get("status") == "open" and prep.get("allowed"):
        proposal = {
            "kind": "invoice",
            "ref_id": invoice["id"],
            "amount": tools.money(invoice["amount"]),
            "account": "checking",
            "reason": f"Pay overdue invoice {invoice['id']} ({invoice['description']}) so {vendor.get('name')} can ship. Due {invoice['due_date']}, shop today is {today}.",
        }
        state.set_pending(ticket_id, proposal)
        _say(
            count,
            ticket_id,
            "accounting",
            f"Invoice {invoice['id']} is open for ${tools.money(invoice['amount']):.2f}, due {invoice['due_date']}, which is before shop today {today}, so it is overdue. Checking has ${prep['balance']:.2f}, so the payment fits. I prepared it. I will not move cash. A human has to approve.",
            "prepare_payment_request",
            {"amount": invoice["amount"]},
            prep,
        )
        _say(count, ticket_id, "boss", f"Accounting prepared ${proposal['amount']:.2f} for invoice {invoice['id']}. Ticket {ticket_id} stays open until a human approves.")
        return _ok(ticket_id, "awaiting_approval", proposal)

    reason = prep.get("reason") or invoice.get("error") or "invoice is not an open overdue bill"
    _say(count, ticket_id, "accounting", f"I am not preparing a payment. {reason}.", "prepare_payment_request", {"amount": invoice.get("amount")}, prep)
    return _finish_open(ticket_id, count, f"Could not prepare the reprint payment. {reason}.")


def _rent(ticket: dict, desk: dict, count: list[int]) -> dict:
    ticket_id = ticket["id"]
    _say(
        count,
        ticket_id,
        "boss",
        f"Ticket {ticket_id} is a rent notice from {ticket['requester']}. I am calling Facilities first because this is the shop space, not a product. I am not calling Inventory.",
    )
    lease = tools.get_lease(int(ticket["lease_id"]))
    if "error" in lease:
        return _finish_open(ticket_id, count, lease["error"])
    today = desk["date_today"]
    gap = tools.days_until(today, lease["next_due"])
    _say(
        count,
        ticket_id,
        "facilities",
        f"Lease {lease['id']} is {lease['space_name']} from {lease['landlord']}. Monthly rent is ${tools.money(lease['monthly_rent']):.2f}. Next due {lease['next_due']}. Shop today is {today}, so the due date is {gap} days away. I cannot pay rent. Accounting should prepare ${tools.money(lease['monthly_rent']):.2f}.",
        "get_lease",
        {"lease_id": lease["id"]},
        lease,
    )
    prep = tools.prepare_payment_request(lease["monthly_rent"])
    if not prep.get("allowed"):
        _say(count, ticket_id, "accounting", f"I refuse the rent payment of ${tools.money(lease['monthly_rent']):.2f}. {prep.get('reason')}. Checking is ${prep.get('balance')}.", "prepare_payment_request", {"amount": lease["monthly_rent"]}, prep)
        return _finish_open(ticket_id, count, "Rent payment refused because checking cannot cover it.")
    proposal = {
        "kind": "rent",
        "ref_id": lease["id"],
        "amount": tools.money(lease["monthly_rent"]),
        "account": "checking",
        "reason": f"Pay {lease['space_name']} rent to {lease['landlord']}. Due {lease['next_due']}, {gap} days after {today}.",
    }
    state.set_pending(ticket_id, proposal)
    _say(
        count,
        ticket_id,
        "accounting",
        f"Checking has ${prep['balance']:.2f}. Rent of ${proposal['amount']:.2f} fits, so I prepared it. Cash does not move until a human approves.",
        "prepare_payment_request",
        {"amount": lease["monthly_rent"]},
        prep,
    )
    _say(count, ticket_id, "boss", f"Facilities confirmed the lease and Accounting prepared ${proposal['amount']:.2f}. Ticket {ticket_id} waits for a human.")
    return _ok(ticket_id, "awaiting_approval", proposal)


def _price(ticket: dict, desk: dict, count: list[int]) -> dict:
    ticket_id = ticket["id"]
    _say(
        count,
        ticket_id,
        "boss",
        f"Ticket {ticket_id} is a bulk price request from {ticket['requester']} for {ticket['qty']} {ticket['sku']} size {ticket['size']}. I am calling Inventory first to count size {ticket['size']}. Customer Service will draft the reply after Accounting checks the margin and the cash. I am not calling Facilities.",
    )
    stock = tools.check_inventory(ticket["sku"], ticket["size"])
    price = tools.get_pricing(ticket["sku"])
    vendor = tools.vendor_for_sku(ticket["sku"])
    bills = tools.vendor_open_invoices(vendor["id"]) if "error" not in vendor else []
    cash = tools.get_cash_account()
    if "error" in stock or "error" in price or "error" in vendor or "error" in cash:
        return _finish_open(ticket_id, count, "A shop lookup failed, so the discount quote is not ready.")
    on_hand = int(stock["qty"])
    requested = int(ticket["qty"])
    shortfall = max(requested - on_hand, 0)
    quote = tools.money(float(price["list_price"]) * 0.85)
    if requested < 10 or tools.cents(quote) <= tools.cents(price["unit_cost"]):
        quote = tools.money(price["list_price"])
    purchase = tools.money(shortfall * float(price["unit_cost"]))
    blocked = len(bills) > 0
    _say(
        count,
        ticket_id,
        "inventory",
        f"{stock['name']} size {stock['size']} has qty {on_hand} in {stock['location']}. The club asked for {requested}, so the shortfall is {shortfall}. {vendor['name']} lead time is {vendor['lead_days']} days. Open unpaid invoices: {len(bills)}. A vendor with an open bill will not ship.",
        "check_inventory",
        {"sku": ticket["sku"], "size": ticket["size"]},
        {"stock": stock, "vendor": vendor, "open_invoices": bills},
    )
    if shortfall == 0:
        pay_line = "No purchase is needed."
        refused = False
    elif blocked:
        pay_line = f"I will not place a ${purchase:.2f} purchase for {shortfall} units. {vendor['name']} still has an open invoice and will not ship."
        refused = True
    elif tools.cents(purchase) > tools.cents(cash["balance"]):
        pay_line = f"I refuse the ${purchase:.2f} purchase for {shortfall} units at the ${tools.money(price['unit_cost']):.2f} unit cost. Checking has ${cash['balance']:.2f}. That payment would go negative."
        refused = True
    else:
        proposal = {
            "kind": "purchase",
            "ref_id": vendor["id"],
            "amount": purchase,
            "sku": ticket["sku"],
            "size": ticket["size"],
            "qty": shortfall,
            "account": "checking",
            "reason": (
                f"Buy {shortfall} more {stock['name']} size {stock['size']} from {vendor['name']} "
                f"at ${tools.money(price['unit_cost']):.2f} each. Checking can cover ${purchase:.2f} and the vendor has no open bill."
            ),
        }
        state.set_pending(ticket_id, proposal)
        _say(
            count,
            ticket_id,
            "accounting",
            f"List price is ${tools.money(price['list_price']):.2f} and unit cost is ${tools.money(price['unit_cost']):.2f}. A 15% bulk quote is ${quote:.2f}. Checking has ${cash['balance']:.2f}, so I prepared a ${purchase:.2f} purchase for {shortfall} units. A human has to approve before cash or stock changes.",
            "prepare_payment_request",
            {"amount": purchase},
            {"pricing": price, "cash": cash, "purchase": purchase, "allowed": True},
        )
        _say(
            count,
            ticket_id,
            "customer_service",
            f"Draft for {ticket['requester']}: we can offer {min(on_hand, requested)} {stock['name']} size {stock['size']} at ${quote:.2f} each. The other {shortfall} are not on the shelf until a human approves the ${purchase:.2f} restock. This draft stays on the board.",
        )
        _say(count, ticket_id, "boss", f"Accounting prepared a ${purchase:.2f} restock. Ticket {ticket_id} stays open until a human approves.")
        return _ok(ticket_id, "awaiting_approval", proposal)
    sell_qty = min(on_hand, requested)
    _say(
        count,
        ticket_id,
        "accounting",
        f"List price is ${tools.money(price['list_price']):.2f} and unit cost is ${tools.money(price['unit_cost']):.2f}. A 15% bulk quote is ${quote:.2f}, which stays above cost. {pay_line} No cash moves on this ticket.",
        "get_pricing",
        {"sku": ticket["sku"]},
        {"pricing": price, "cash": cash, "purchase": purchase, "refused": refused},
    )
    draft = (
        f"Draft for {ticket['requester']}: we can offer {sell_qty} {stock['name']} size {stock['size']} at ${quote:.2f} each "
        f"(list ${tools.money(price['list_price']):.2f}, cost ${tools.money(price['unit_cost']):.2f}). "
        f"We only have {on_hand} on the shelf. {pay_line} "
        f"This draft stays on the board. Nobody is emailed."
    )
    _say(count, ticket_id, "customer_service", draft)
    note = f"Quoted {sell_qty} at ${quote:.2f}. Shortfall {shortfall} not purchased. {pay_line}"
    tools.set_ticket_status(ticket_id, "resolved", note)
    _say(count, ticket_id, "boss", f"Inventory, Accounting, and Customer Service finished ticket {ticket_id}. No payment was prepared. I am marking it resolved.")
    return _ok(ticket_id, "resolved")


def approve(ticket_id: int, approved_by: str) -> dict:
    proposal = state.pop_pending(ticket_id)
    if proposal is None:
        return {"ok": False, "ticket_id": ticket_id, "status": "open", "summary": state.summaries_for(ticket_id), "error": "nothing is waiting for approval"}
    result = tools.apply_approved_payment(
        kind=proposal["kind"],
        amount=proposal["amount"],
        approved_by=approved_by,
        ref_id=int(proposal["ref_id"]),
        sku=proposal.get("sku"),
        size=proposal.get("size"),
        qty=proposal.get("qty"),
        account=proposal.get("account", "checking"),
    )
    count = [0]
    if not result.get("ok"):
        state.set_pending(ticket_id, proposal)
        state.append_step(ticket_id, "accounting", f"The human approval did not change cash. {result.get('error')}", "apply_approved_payment", proposal, result)
        return {"ok": False, "ticket_id": ticket_id, "status": "awaiting_approval", "summary": state.summaries_for(ticket_id), "error": result.get("error"), "proposal": proposal}

    state.append_step(
        ticket_id,
        "accounting",
        f"Human {approved_by} approved the {proposal['kind']} payment of ${result['amount']:.2f}. Checking is now ${result['balance']:.2f}.",
        "apply_approved_payment",
        proposal,
        result,
    )
    ticket = tools.get_ticket(ticket_id)
    if proposal["kind"] == "invoice":
        vendor = tools.vendor_for_sku(ticket["sku"])
        draft = (
            f"Draft for {ticket['requester']}: size {ticket['size']} of {ticket['sku']} is still qty 0. "
            f"Invoice {proposal['ref_id']} for ${result['amount']:.2f} was paid on {result['paid_at']} after {approved_by} approved it. "
            f"{vendor.get('name')} lead time is {vendor.get('lead_days')} days, so the reprint is not on the shelf today. "
            f"This draft stays on the board."
        )
        _say(count, ticket_id, "customer_service", draft)
        note = f"Paid invoice {proposal['ref_id']} for ${result['amount']:.2f} on {result['paid_at']}. Reprint lead time {vendor.get('lead_days')} days. Stock was not increased today."
    elif proposal["kind"] == "rent":
        lease = tools.get_lease(int(proposal["ref_id"]))
        state.append_step(
            ticket_id,
            "facilities",
            f"Rent payment is on the books. {lease.get('space_name')} next due date is now {lease.get('next_due')}.",
            "get_lease",
            {"lease_id": proposal["ref_id"]},
            lease,
        )
        note = f"Paid rent ${result['amount']:.2f} on {result['paid_at']}. Next due {lease.get('next_due')}."
    else:
        stock = tools.check_inventory(proposal.get("sku") or "", proposal.get("size") or "")
        note = (
            f"Paid {proposal['kind']} ${result['amount']:.2f} on {result['paid_at']}. "
            f"On hand for {proposal.get('sku')} size {proposal.get('size')} is now {stock.get('qty')}."
        )
    tools.set_ticket_status(ticket_id, "resolved", note)
    state.append_step(ticket_id, "boss", f"The human payment is recorded and ticket {ticket_id} is resolved. {note}")
    return _ok(ticket_id, "resolved")


def _finish_open(ticket_id: int, count: list[int], reason: str) -> dict:
    _say(count, ticket_id, "boss", f"Ticket {ticket_id} stays open. {reason}")
    return _ok(ticket_id, "open", error=reason)


def _ok(ticket_id: int, status: str, proposal: dict | None = None, error: str | None = None) -> dict:
    return {
        "ok": error is None,
        "ticket_id": ticket_id,
        "status": status,
        "summary": state.summaries_for(ticket_id),
        "proposal": proposal,
        "error": error,
    }
