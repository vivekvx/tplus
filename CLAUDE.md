# tplus — Settlement Reconciliation Engine

## What this is
Demo fintech project modeling the T+1/T+2 settlement timing gap that causes cash-flow volatility in payment gateways (modeled after Pine Labs' publicly reported working-capital swings).

## Commands
```bash
# Setup
cd ~/tplus && .venv/bin/pip install -r requirements.txt

# Tests
.venv/bin/python -m pytest -q

# Run server
.venv/bin/uvicorn app.main:app --reload

# Frontend
cd frontend && npm run dev
```

## Architecture
```
app/
├── db.py           SQLite + SQLAlchemy
├── models.py       ORM (Transaction, Settlement, SettlementLine, LedgerEntry, ReconResult)
├── ledger.py       Double-entry core: post(), invariant, domain events
├── recon.py        Reconciliation engine (match txns ↔ settlement lines)
├── generator.py    Synthetic data: messy bank CSV + gateway txns
├── routes.py       FastAPI endpoints
tests/
├── test_ledger.py  Invariant + float gap tests
frontend/           Next.js dashboard (float curve + exceptions table)
```

## Constraints

### Money
- ALL amounts are integer paise. ₹1850.50 = 185050. NEVER use float for money.
- Format to rupees only at display/API response layer.

### Double-entry ledger
- Every event posts >=2 legs summing to zero. `post()` in ledger.py rejects unbalanced.
- `assert_balanced(db)` must pass after every write. Tests enforce this.
- Ledger is append-only. Never UPDATE or DELETE a LedgerEntry row.
- 4 accounts: MERCHANT_PAYABLE, BANK_RECEIVABLE, PINE_FLOAT, FEE_INCOME.

### Recon
- Hero case: many-to-one (1 bank deposit = N txns netted, with fees deducted). Must un-bundle.
- Statuses: MATCHED | MISSING | AMOUNT_MISMATCH | DUPLICATE | FEE_DRIFT

### Scope (ponytail)
- Single currency (INR). Single CSV settlement format.
- SQLite for demo. No auth/sessions. No reversals/chargebacks.
- No ML forecaster. Float curve from real recon data only.

## Framing
This is a modeled scenario, NOT Pine Labs' disclosed financial data.
Frame as: "models the early-pay/late-settle working-capital gap that payment gateways face."

## Python
Always use `.venv/bin/python` and `.venv/bin/pip`.
