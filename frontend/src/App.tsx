import { useCallback, useEffect, useState } from "react";

const API = "http://localhost:8000";

type Proposal = { kind: string; amount: number; reason: string };
type Ticket = {
  id: number;
  type: string;
  requester: string;
  subject: string;
  status: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  notes: string | null;
  pending_approval: boolean;
  proposal: Proposal | null;
};
type DeskEvent = { ts: string; ticket_id: number; agent: string; text: string; tool: string | null };
type Cash = { name: string; balance: number; date: string };

const AGENTS = ["boss", "inventory", "accounting", "facilities", "customer_service"] as const;

function ticketFromUrl(): number {
  const asked = Number(new URLSearchParams(window.location.search).get("ticket"));
  return asked === 101 || asked === 102 || asked === 103 ? asked : 101;
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [cash, setCash] = useState<Cash | null>(null);
  const [selected, setSelected] = useState<number>(ticketFromUrl);
  const [events, setEvents] = useState<DeskEvent[]>([]);
  const [approver, setApprover] = useState("Kay");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [ticketRes, cashRes, eventRes] = await Promise.all([
      fetch(`${API}/tickets`),
      fetch(`${API}/cash`),
      fetch(`${API}/events`),
    ]);
    const nextTickets = (await ticketRes.json()) as Ticket[];
    setTickets(nextTickets);
    setCash(await cashRes.json());
    setEvents(await eventRes.json());
  }, []);

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
    const timer = setInterval(() => {
      load().catch(() => undefined);
    }, 1500);
    return () => clearInterval(timer);
  }, [load]);

  const ticket = tickets.find((item) => item.id === selected);
  const mine = events.filter((item) => item.ticket_id === selected);

  async function runTeam() {
    setBusy(true);
    setError("");
    const res = await fetch(`${API}/tickets/${selected}/run`, { method: "POST" });
    const body = await res.json();
    if (!body.ok && body.error) setError(body.error);
    await load();
    setBusy(false);
  }

  async function approve() {
    setBusy(true);
    setError("");
    const res = await fetch(`${API}/approve-pay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticket_id: selected, approved_by: approver }),
    });
    const body = await res.json();
    if (!body.ok && body.error) setError(body.error);
    await load();
    setBusy(false);
  }

  return (
    <main className="desk">
      <header>
        <div>
          <p className="eyebrow">Chapel Street</p>
          <h1>Campus Customs desk</h1>
        </div>
        <div className="cash">
          <span>Checking</span>
          <strong>${cash ? cash.balance.toFixed(2) : "—"}</strong>
          <small>{cash?.date}</small>
        </div>
      </header>
      <section className="board">
        {tickets.map((item) => (
          <button
            key={item.id}
            className={item.id === selected ? "ticket on" : "ticket"}
            onClick={() => {
              setSelected(item.id);
              const url = new URL(window.location.href);
              url.searchParams.set("ticket", String(item.id));
              window.history.replaceState({}, "", url);
            }}
          >
            <b>#{item.id}</b>
            <span>{item.subject}</span>
            <em className={item.status}>{item.status}</em>
            {item.pending_approval && <em className="wait">needs approval</em>}
          </button>
        ))}
      </section>
      {ticket && (
        <section className="work">
          <div className="story">
            <h2>
              {ticket.subject} · {ticket.requester}
            </h2>
            <p>
              {ticket.type}
              {ticket.sku ? ` · ${ticket.qty} × ${ticket.sku} ${ticket.size}` : ""}
            </p>
            <div className="actions">
              <button disabled={busy || ticket.status === "resolved"} onClick={runTeam}>
                Run the team
              </button>
              <label>
                Human approver
                <input value={approver} onChange={(event) => setApprover(event.target.value)} />
              </label>
              <button disabled={busy || !ticket.pending_approval} onClick={approve}>
                Approve pay {ticket.proposal ? `$${ticket.proposal.amount.toFixed(2)}` : ""}
              </button>
            </div>
            {ticket.proposal && <p className="reason">{ticket.proposal.reason}</p>}
            {error && <p className="error">{error}</p>}
            {ticket.notes && <p className="notes">{ticket.notes}</p>}
          </div>
          <div className="agents">
            {AGENTS.map((agent) => {
              const lines = mine.filter((item) => item.agent === agent);
              return (
                <article key={agent} className={agent}>
                  <h3>{agent.replace("_", " ")}</h3>
                  {lines.length === 0 && <p className="quiet">No turn on this ticket yet.</p>}
                  {lines.map((line) => (
                    <p key={line.ts + line.text}>
                      {line.text}
                      {line.tool && <small> · {line.tool}</small>}
                    </p>
                  ))}
                </article>
              );
            })}
          </div>
        </section>
      )}
    </main>
  );
}
