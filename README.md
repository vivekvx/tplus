# tplus — Settlement Reconciliation Engine

When a customer pays a merchant through a payment gateway, the merchant gets paid on day T+1, but the bank settles the money on day T+2 or T+3. During that gap, the payment gateway is floating cash — money has gone out but hasn't come back yet. **tplus** models this problem: it generates realistic transaction data, matches bank settlements back to individual transactions, flags mismatches, and shows you exactly how much cash is floating on any given day.

This is a modeled scenario built to demonstrate the reconciliation problem, not real financial data.

![tplus dashboard](docs/screenshot.png)

## What it does

1. **Generates 1,000 synthetic transactions** over 30 days with realistic messiness — batched settlements, fee deductions (MDR + GST), missing records, duplicates
2. **Matches bank settlements to transactions** using a many-to-one reconciliation engine (one bank deposit = multiple transactions netted together)
3. **Flags problems** — missing transactions, duplicates, amount mismatches, fee drift, orphan settlements
4. **Tracks every rupee** with a double-entry ledger that must always sum to zero
5. **Shows the float gap** — a daily chart of how much cash is out the door but not yet settled

## Tech stack

| Layer | Tool |
|-------|------|
| Backend API | Python 3.9, FastAPI |
| Database | SQLite via SQLAlchemy |
| Frontend | Next.js 15, React, Tailwind CSS |
| Charts | Recharts |
| Animations | Framer Motion |
| Money handling | Integer paise (no floating point — ₹1,850.50 = 185050) |

## How to run it

You need Python 3.9+ and Node.js 18+.

**1. Set up the backend**

```bash
cd tplus
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Backend starts at `http://localhost:8000`.

**2. Set up the frontend**

```bash
cd frontend
npm install
npm run dev
```

Frontend starts at `http://localhost:3000`.

**3. Use it**

- Open `http://localhost:3000` in your browser
- Click **Run Pipeline** — this generates transactions, ingests bank settlements, and runs reconciliation in one click
- The dashboard shows:
  - **Trial balance** — four accounts (Merchant Payable, Bank Receivable, Pine Float, Fee Income) and whether the ledger is balanced
  - **Float curve** — daily chart of the cash gap between payouts and settlements
  - **Recon summary** — counts of matched, missing, duplicate, fee drift, and other statuses
  - **Exceptions table** — every transaction that didn't match cleanly, with status and amount

**4. Run tests**

```bash
.venv/bin/python -m pytest -q
```

9 tests covering the ledger invariant, many-to-one batch matching, and all 5 exception types.

## How it works inside

```
app/
├── main.py        → FastAPI app with CORS
├── db.py          → SQLite + SQLAlchemy setup
├── models.py      → 5 tables: Transaction, Settlement, SettlementLine, LedgerEntry, ReconResult
├── ledger.py      → Double-entry posting (rejects if sum ≠ 0)
├── generator.py   → Creates 1,000 transactions + messy bank CSV
├── recon.py       → Matches settlements to transactions, flags exceptions
└── routes.py      → 8 API endpoints

frontend/app/
└── page.tsx       → Single-page dashboard with charts and tables
```

The ledger enforces one rule: **every entry must have a balancing counterpart**. If you debit Merchant Payable, you must credit Bank Receivable by the same amount. The system checks this after every reconciliation run.

## API endpoints

| Method | Path | What it does |
|--------|------|-------------|
| POST | `/pipeline` | One-click: generate → ingest → reconcile |
| POST | `/generate` | Create fresh transaction + settlement data |
| POST | `/settlements/ingest` | Parse bank CSV into database |
| POST | `/recon/run` | Run the matching engine |
| GET | `/recon/summary` | Status counts (matched, missing, etc.) |
| GET | `/recon/exceptions` | Non-matched items with details |
| GET | `/float/daily` | Daily cumulative float balance |
| GET | `/ledger/balance` | Trial balance across all 4 accounts |

## Contributing

1. Fork the repo
2. Create a branch (`git checkout -b fix/your-fix`)
3. Make changes and run `pytest` to make sure nothing breaks
4. Open a pull request with a short description of what changed and why

Keep it simple — no unnecessary abstractions, no features beyond what's needed.

## License

MIT
