"""FastMCP server for Campus Customs. Run from the project root."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastmcp import FastMCP

from mcp_server import tools

mcp = FastMCP("campus-customs")


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Read one row from tickets."""
    return tools.get_ticket(ticket_id)


@mcp.tool
def check_inventory(sku: str, size: str) -> dict:
    """Read qty and location for one sku and size from inventory."""
    return tools.check_inventory(sku, size)


@mcp.tool
def get_invoice(invoice_id: int) -> dict:
    """Read one row from invoices."""
    return tools.get_invoice(invoice_id)


@mcp.tool
def get_lease(lease_id: int) -> dict:
    """Read one row from leases."""
    return tools.get_lease(lease_id)


@mcp.tool
def list_vendors() -> list[dict]:
    """Read every vendor, including lead_days."""
    return tools.list_vendors()


@mcp.tool
def vendor_for_sku(sku: str) -> dict:
    """Pick the vendor whose specialty matches this sku."""
    return tools.vendor_for_sku(sku)


@mcp.tool
def vendor_open_invoices(vendor_id: int) -> list[dict]:
    """Read open invoices for one vendor. An open bill means they will not ship."""
    return tools.vendor_open_invoices(vendor_id)


@mcp.tool
def get_pricing(sku: str) -> dict:
    """Read unit_cost and list_price for one sku."""
    return tools.get_pricing(sku)


@mcp.tool
def get_cash_account(name: str = "checking") -> dict:
    """Read one cash_accounts row."""
    return tools.get_cash_account(name)


@mcp.tool
def get_desk() -> dict:
    """Read desk.date_today. That date is 'today' for the shop."""
    return tools.get_desk()


@mcp.tool
def list_tickets() -> list[dict]:
    """Read every ticket."""
    return tools.list_tickets()


@mcp.tool
def prepare_payment_request(amount: float, account: str = "checking") -> dict:
    """Check checking cash. Does not move money."""
    return tools.prepare_payment_request(amount, account)


@mcp.tool
def apply_approved_payment(
    kind: str,
    amount: float,
    approved_by: str,
    ref_id: int,
    sku: str | None = None,
    size: str | None = None,
    qty: int | None = None,
    account: str = "checking",
) -> dict:
    """Move cash only when a human has approved. Updates payments and the related table."""
    return tools.apply_approved_payment(
        kind, amount, approved_by, ref_id, sku, size, qty, account
    )


@mcp.tool
def set_ticket_status(ticket_id: int, status: str, notes: str) -> dict:
    """Set a ticket to open or resolved and store the outcome note."""
    return tools.set_ticket_status(ticket_id, status, notes)


if __name__ == "__main__":
    mcp.run()
