"""Data shapes for the desk API. Shop rows stay in the database."""

from pydantic import BaseModel, Field


class ApprovePay(BaseModel):
    ticket_id: int
    approved_by: str = Field(min_length=1)


class TicketView(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    status: str
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    notes: str | None = None
    pending_approval: bool = False
    proposal: dict | None = None


class RunResult(BaseModel):
    ok: bool
    ticket_id: int
    status: str
    summary: dict
    proposal: dict | None = None
    error: str | None = None


class CashView(BaseModel):
    name: str
    balance: float
    date: str
