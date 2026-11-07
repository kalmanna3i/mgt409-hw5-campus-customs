# Campus Customs multi-agent desk

Homework 5 shop team for Campus Customs. Agents read and update `data/campus_customs_new.db` only through the MCP tools in `mcp_server/`. `data/campus_customs.db` stays the clean original.

## Reset, then run

Copy the original database over the working copy when you want a clean shop:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

Or `POST http://localhost:8000/reset` after the backend is up. Reset does not delete `output/audit_trail.json`.

## Start the MCP server

From the project root:

```bash
python3 mcp_server/server.py
```

Cursor can launch that same command from `.mcp.json`.

## Start the API

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API is at `http://localhost:8000`. Put your key in `.env` as `PORTKEY_API_KEY`. Every agent uses `gpt-6-luna` through Portkey.

## Start the React board

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Pick a ticket, run the team, and approve a pay when the button shows an amount. Checking drops only after that approval.

Before a full three-ticket run, reset the database. A clean order is ticket 101 (approve the $840 invoice), ticket 102 (approve the $2400 rent), then ticket 103 (no payment: the $264 hoodie restock is refused because checking would go negative).
