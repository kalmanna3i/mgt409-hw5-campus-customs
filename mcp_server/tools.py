"""Shop facts and the only writes against campus_customs_new.db."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "campus_customs_new.db"
ORIGINAL_PATH = ROOT / "data" / "campus_customs.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _one(sql: str, params: tuple = ()) -> dict | None:
    found = _rows(sql, params)
    return found[0] if found else None


def money(value: float) -> float:
    return round(float(value) + 0.0, 2)


def cents(value: float) -> int:
    return int(round(float(value) * 100))


def get_desk() -> dict:
    row = _one("SELECT date_today, notes FROM desk LIMIT 1")
    if row is None:
        return {"error": "desk table is empty"}
    return row


def list_tickets() -> list[dict]:
    return _rows("SELECT * FROM tickets ORDER BY id")


def get_ticket(ticket_id: int) -> dict:
    row = _one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if row is None:
        return {"error": f"no ticket {ticket_id}"}
    return row


def check_inventory(sku: str, size: str) -> dict:
    row = _one(
        "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
        (sku, size),
    )
    if row is None:
        return {"error": "no inventory row", "sku": sku, "size": size}
    return row


def get_invoice(invoice_id: int) -> dict:
    row = _one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    if row is None:
        return {"error": f"no invoice {invoice_id}"}
    return row


def get_lease(lease_id: int) -> dict:
    row = _one("SELECT * FROM leases WHERE id = ?", (lease_id,))
    if row is None:
        return {"error": f"no lease {lease_id}"}
    return row


def list_vendors() -> list[dict]:
    return _rows("SELECT id, name, specialty, lead_days FROM vendors ORDER BY id")


def vendor_for_sku(sku: str) -> dict:
    sku_u = sku.upper()
    if "MUG" in sku_u:
        needle = "mug"
    elif any(token in sku_u for token in ("TEE", "HOOD", "HAT")):
        needle = "apparel"
    else:
        return {"error": f"no vendor specialty for {sku}"}
    matches = [v for v in list_vendors() if needle in v["specialty"].lower()]
    if len(matches) != 1:
        return {"error": "vendor match was not unique", "sku": sku, "matches": matches}
    return matches[0]


def vendor_open_invoices(vendor_id: int) -> list[dict]:
    return _rows(
        "SELECT * FROM invoices WHERE vendor_id = ? AND status = 'open' ORDER BY id",
        (vendor_id,),
    )


def get_pricing(sku: str) -> dict:
    row = _one("SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))
    if row is None:
        return {"error": f"no pricing for {sku}"}
    return row


def get_cash_account(name: str = "checking") -> dict:
    row = _one("SELECT name, balance, date FROM cash_accounts WHERE name = ?", (name,))
    if row is None:
        return {"error": f"no cash account {name}"}
    row["balance"] = money(row["balance"])
    return row


def prepare_payment_request(amount: float, account: str = "checking") -> dict:
    """Read cash and say whether a human could approve this amount. Does not move cash."""
    cash = get_cash_account(account)
    if "error" in cash:
        return cash
    amount = money(amount)
    allowed = cents(cash["balance"]) >= cents(amount) and cents(amount) > 0
    return {
        "account": account,
        "amount": amount,
        "balance": cash["balance"],
        "allowed": allowed,
        "reason": "enough checking cash" if allowed else "refused: payment would make checking negative or is not positive",
    }


def _add_month(iso_day: str) -> str:
    year, month, day = (int(part) for part in iso_day.split("-"))
    month += 1
    if month == 13:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}-{day:02d}"


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
    """Move cash only after a human approves. Refuses a negative balance or a second pay."""
    if not approved_by or approved_by.strip().lower() in {"agent", "boss", "accounting"}:
        return {"ok": False, "error": "a human name is required to approve a payment"}
    amount = money(amount)
    desk = get_desk()
    paid_at = desk.get("date_today")
    if not paid_at:
        return {"ok": False, "error": "desk.date_today is missing"}

    with connect() as conn:
        already = conn.execute(
            "SELECT id FROM payments WHERE kind = ? AND ref_id = ?",
            (kind, ref_id),
        ).fetchone()
        if already is not None and kind in {"invoice", "rent"}:
            return {"ok": False, "error": f"{kind} {ref_id} was already paid"}

        if kind == "invoice":
            inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if inv is None:
                return {"ok": False, "error": f"no invoice {ref_id}"}
            if inv["status"] != "open":
                return {"ok": False, "error": f"invoice {ref_id} is {inv['status']}"}
            if cents(inv["amount"]) != cents(amount):
                return {"ok": False, "error": "amount does not match the invoice"}
        elif kind == "rent":
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                return {"ok": False, "error": f"no lease {ref_id}"}
            if cents(lease["monthly_rent"]) != cents(amount):
                return {"ok": False, "error": "amount does not match monthly rent"}
        elif kind == "purchase":
            if not sku or not size or not qty or qty <= 0:
                return {"ok": False, "error": "purchase needs sku, size, and qty"}
            price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
            if price is None:
                return {"ok": False, "error": f"no pricing for {sku}"}
            expected = money(float(price["unit_cost"]) * int(qty))
            if cents(expected) != cents(amount):
                return {"ok": False, "error": "amount does not match qty times unit cost"}
        else:
            return {"ok": False, "error": f"unknown payment kind {kind}"}

        cash = conn.execute(
            "SELECT balance FROM cash_accounts WHERE name = ?",
            (account,),
        ).fetchone()
        if cash is None:
            return {"ok": False, "error": f"no cash account {account}"}
        if cents(cash["balance"]) < cents(amount):
            return {"ok": False, "error": "refused: not enough checking cash"}

        new_balance = money((cents(cash["balance"]) - cents(amount)) / 100.0)
        conn.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
            (new_balance, paid_at, account),
        )
        conn.execute(
            """
            INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kind, ref_id, amount, account, paid_at, approved_by.strip()),
        )
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
        elif kind == "rent":
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (ref_id,)).fetchone()
            nxt = _add_month(lease["next_due"])
            conn.execute(
                "UPDATE leases SET next_due = ?, notes = ? WHERE id = ?",
                (nxt, f"Paid {amount:.2f} on {paid_at} after human approval by {approved_by.strip()}", ref_id),
            )
        elif kind == "purchase":
            updated = conn.execute(
                "UPDATE inventory SET qty = qty + ? WHERE sku = ? AND size = ?",
                (qty, sku, size),
            )
            if updated.rowcount != 1:
                conn.rollback()
                return {"ok": False, "error": "inventory row missing for purchase"}
        conn.commit()

    return {
        "ok": True,
        "kind": kind,
        "ref_id": ref_id,
        "amount": amount,
        "account": account,
        "paid_at": paid_at,
        "approved_by": approved_by.strip(),
        "balance": get_cash_account(account)["balance"],
    }


def set_ticket_status(ticket_id: int, status: str, notes: str) -> dict:
    if status not in {"open", "resolved"}:
        return {"error": "status must stay open or resolved"}
    with connect() as conn:
        updated = conn.execute(
            "UPDATE tickets SET status = ?, notes = ? WHERE id = ?",
            (status, notes, ticket_id),
        )
        conn.commit()
        if updated.rowcount != 1:
            return {"error": f"no ticket {ticket_id}"}
    return get_ticket(ticket_id)


def reset_working_database() -> dict:
    """Copy the untouched original over the working database."""
    shutil.copy(ORIGINAL_PATH, DB_PATH)
    cash = get_cash_account()
    return {"ok": True, "database": str(DB_PATH.name), "checking": cash}


def days_until(today_iso: str, due_iso: str) -> int:
    return (date.fromisoformat(due_iso) - date.fromisoformat(today_iso)).days
