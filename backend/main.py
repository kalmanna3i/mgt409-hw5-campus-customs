"""Campus Customs desk API. Start with: uvicorn main:app --reload --port 8000"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from backend import state
from backend.models import ApprovePay, CashView, RunResult, TicketView
from backend.orchestrator import approve, run_ticket
from mcp_server import tools

app = FastAPI(title="Campus Customs Desk")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ticket_view(row: dict) -> TicketView:
    pending = state.get_pending(int(row["id"]))
    return TicketView(
        id=row["id"],
        type=row["type"],
        requester=row["requester"],
        subject=row["subject"],
        status=row["status"],
        sku=row.get("sku"),
        size=row.get("size"),
        qty=row.get("qty"),
        lease_id=row.get("lease_id"),
        invoice_id=row.get("invoice_id"),
        notes=row.get("notes"),
        pending_approval=pending is not None,
        proposal=pending,
    )


@app.get("/tickets", response_model=list[TicketView])
def list_tickets():
    return [_ticket_view(row) for row in tools.list_tickets()]


@app.post("/tickets/{ticket_id}/run", response_model=RunResult)
def run_one(ticket_id: int):
    return run_ticket(ticket_id)


@app.get("/events")
def events(ticket_id: int | None = None):
    return state.events_for(ticket_id)


@app.post("/approve-pay", response_model=RunResult)
def approve_pay(body: ApprovePay):
    return approve(body.ticket_id, body.approved_by)


@app.get("/cash", response_model=CashView)
def cash():
    row = tools.get_cash_account()
    return CashView(name=row["name"], balance=row["balance"], date=row["date"])


@app.post("/reset")
def reset():
    state.reset_board()
    return tools.reset_working_database()
