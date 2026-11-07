"""Reset the shop, resolve tickets 101-103, and write the graded output files."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend import state
from backend.orchestrator import approve, run_ticket
from mcp_server import tools

OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)


def smoke() -> None:
    calls = [
        (
            "Complete the homework tests. Check ticket 101 in the working database.",
            "get_ticket",
            {"ticket_id": 101},
            tools.get_ticket(101),
        ),
        (
            "Complete the homework tests. Check navy hoodie size M stock.",
            "check_inventory",
            {"sku": "CC-HOOD-NAVY", "size": "M"},
            tools.check_inventory("CC-HOOD-NAVY", "M"),
        ),
        (
            "Complete the homework tests. Read invoice 501.",
            "get_invoice",
            {"invoice_id": 501},
            tools.get_invoice(501),
        ),
    ]
    payload = [
        {"prompt": prompt, "tool": name, "tool_input": tool_input, "output": output}
        for prompt, name, tool_input, output in calls
    ]
    (OUT / "mcp_smoke.json").write_text(json.dumps(payload, indent=2))


def main() -> None:
    original = (ROOT / "data" / "campus_customs.db").read_bytes()
    state.reset_board()
    tools.reset_working_database()
    smoke()
    start = tools.get_cash_account()["balance"]
    assert start == 3400.0, start

    first = run_ticket(101)
    assert first["status"] == "awaiting_approval", first
    paid_101 = approve(101, "Kay")
    assert paid_101["status"] == "resolved", paid_101
    after_101 = tools.get_cash_account()["balance"]
    assert after_101 == 2560.0, after_101

    second = run_ticket(102)
    assert second["status"] == "awaiting_approval", second
    paid_102 = approve(102, "Kay")
    assert paid_102["status"] == "resolved", paid_102
    after_102 = tools.get_cash_account()["balance"]
    assert after_102 == 160.0, after_102

    third = run_ticket(103)
    assert third["status"] == "resolved", third
    end = tools.get_cash_account()["balance"]
    assert end == 160.0, end

    tickets = {row["id"]: row for row in tools.list_tickets()}
    assert all(tickets[i]["status"] == "resolved" for i in (101, 102, 103))
    assert (ROOT / "data" / "campus_customs.db").read_bytes() == original

    conn = sqlite3.connect(ROOT / "data" / "campus_customs_new.db")
    pays = conn.execute("SELECT kind, ref_id, amount, approved_by FROM payments ORDER BY id").fetchall()
    invoice = conn.execute("SELECT status FROM invoices WHERE id = 501").fetchone()[0]
    lease_due = conn.execute("SELECT next_due FROM leases WHERE id = 1").fetchone()[0]
    conn.close()
    assert pays == [("invoice", 501, 840.0, "Kay"), ("rent", 1, 2400.0, "Kay")], pays
    assert invoice == "paid"
    assert lease_due == "2026-10-02", lease_due

    resolved = []
    for ticket_id, outcome in (
        (101, "Paid overdue reprint invoice 501 for $840 so Bulldog Print Co can ship. Size S tee is still not on the shelf today."),
        (102, "Paid Chapel Street rent of $2400. Next due date moved to 2026-10-02."),
        (103, "Quoted 8 navy hoodies at $49.30. Refused a $264 restock because checking had $160."),
    ):
        summary = state.summaries_for(ticket_id)
        resolved.append(
            {
                "id": ticket_id,
                "final_status": "resolved",
                "outcome": outcome,
                "agents": {name: " ".join(lines) for name, lines in summary.items()},
                "human_approvals": [
                    {"approved_by": "Kay", "kind": kind, "ref_id": ref, "amount": amount}
                    for kind, ref, amount, _who in pays
                    if (ticket_id == 101 and kind == "invoice") or (ticket_id == 102 and kind == "rent")
                ]
                if ticket_id in (101, 102)
                else [],
            }
        )
    (OUT / "resolved_tickets.json").write_text(json.dumps(resolved, indent=2))
    print("PASS start", start, "after101", after_101, "after102", after_102, "end", end)
    print("payments", pays)


if __name__ == "__main__":
    main()
