# tplus — Product Requirements Document

## One-liner
Settlement reconciliation engine that visualizes the cash-flow gap between paying merchants early (T+1) and receiving bank settlements late (T+2/T+3).

## Problem statement
Payment gateways promise merchants fast payouts (next-day or same-day) to win business. But banks/card networks settle the gateway on their own schedule — 2–3 days later, in netted batches, with fees silently deducted. This timing gap forces the gateway to float its own cash. The float swings violently with transaction volume (festivals, weekends), creating unpredictable operating cash flow.

Pine Labs publicly reported OCF swings of -₹281Cr to +₹152Cr to -₹152Cr across consecutive quarters in FY25-26, driven by this exact mechanic. No student project models this problem.

## Target user
Pine Labs hiring manager / fintech interviewer evaluating an intern candidate's domain understanding.

## Success criteria
1. Interviewer sees the float curve and immediately recognizes their own cash-flow problem.
2. Exceptions table shows realistic recon failures (missing txns, fee drift, batch un-bundling).
3. Double-entry ledger passes invariant test — debits == credits, always.
4. Candidate can explain the T+1/T+2 settlement timing, RBI nodal account mechanics, and MDR fee flow in a follow-up conversation.

## Non-goals
- NOT a production system. Synthetic data only.
- NOT Pine Labs' disclosed financials. Modeled scenario.
- No auth, multi-tenancy, multi-currency, reversals, chargebacks.
- No ML forecasting. Float shown from actual recon data, not predictions.

---

## Features

### F1: Double-entry ledger (core)
**What:** Append-only ledger where every event posts ≥2 entries summing to zero.
**Accounts:** MERCHANT_PAYABLE, BANK_RECEIVABLE, PINE_FLOAT, FEE_INCOME.
**Invariant:** `SUM(amount_paise) == 0` across all rows. Enforced in code + test.
**Money:** Integer paise everywhere. ₹1850.50 = 185050. Never float.

**Domain events:**
| Event | Debit (+) | Credit (-) |
|---|---|---|
| Merchant payout (T+1) | BANK_RECEIVABLE (gross) | PINE_FLOAT (net), FEE_INCOME (fee) |
| Bank settlement (T+2/T+3) | PINE_FLOAT (net received), FEE_INCOME (bank's fee) | BANK_RECEIVABLE (gross) |

**Why this matters:** A fintech reviewer checks this first. If debits ≠ credits, they stop reading.

### F2: Synthetic data generator
**What:** Script that produces:
- 1000 gateway transactions over 30 simulated days (varied merchants, amounts ₹200–₹50,000, random hours).
- Matching settlement CSV with realistic mess:

| Mess type | Rate | What happens |
|---|---|---|
| Netted batch | ~40% of settlements | 1 bank deposit covers 5–15 txns. Must un-bundle. |
| Fee deduction | 100% | Bank deducts MDR (1.5–2%) + GST (18% on MDR) from gross. Net ≠ gross. |
| Missing txn | ~2% | Txn exists in gateway, no matching settlement line. |
| Duplicate | ~1% | Same txn ref appears twice in settlement file. |
| T+2/T+3 delay | 100% | Settlement value_date is 2–3 business days after txn date. |

**Output:** `data/transactions.json` + `data/settlements.csv` (the messy bank file).

### F3: Reconciliation engine (the hero)
**What:** Matching pass that takes gateway txns + settlement lines and produces recon results.

**Algorithm:**
1. Parse settlement CSV → Settlement + SettlementLine rows (un-bundle batches).
2. For each SettlementLine, match by `claimed_txn_ref` → gateway txn.
3. Flag statuses:

| Status | Condition |
|---|---|
| MATCHED | Ref matches, gross == txn amount, fee within tolerance |
| MISSING | Gateway txn has no matching settlement line |
| AMOUNT_MISMATCH | Ref matches but gross ≠ txn amount |
| FEE_DRIFT | Ref+gross match but fee differs from expected MDR+GST |
| DUPLICATE | Same txn ref matched by >1 settlement line |

4. For each match, post corresponding ledger entries (record_bank_settlement).
5. Run `assert_balanced()` after full pass.

**Hero case (many-to-one):**
Bank sends ONE deposit of ₹47,200 that settles 10 txns totaling ₹48,000, minus ₹800 MDR+GST. Engine must un-bundle the batch, match each line to its txn, and catch any drift per-line.

### F4: Float curve endpoint
**What:** `GET /float/daily` returns daily PINE_FLOAT balance over the 30-day window.

**Shape:**
```json
[
  {"date": "2026-01-01", "float_paise": -4500000},
  {"date": "2026-01-02", "float_paise": -8200000}
]
```

**The story:** Days with high merchant payouts but no bank settlement = deep negative float. Settlement days = float recovers. Weekends/holidays = float drops further. The curve IS the product.

### F5: Exceptions table endpoint
**What:** `GET /recon/exceptions` returns all non-MATCHED recon results.

**Shape:**
```json
[
  {"txn_id": 42, "status": "MISSING", "amount_display": "₹12,500.00", "note": "No settlement line found"},
  {"txn_id": 87, "status": "FEE_DRIFT", "amount_display": "₹3,200.00", "note": "Expected fee ₹64, got ₹58"}
]
```

### F6: Trial balance endpoint
**What:** `GET /ledger/balance` returns balance per account + total.

**Shape:**
```json
{
  "accounts": {
    "MERCHANT_PAYABLE": 0,
    "BANK_RECEIVABLE": 4500000,
    "PINE_FLOAT": -4200000,
    "FEE_INCOME": -300000
  },
  "total": 0,
  "balanced": true
}
```

### F7: Dashboard (single page)
**What:** One Next.js page with two panels:
1. **Float curve** — line chart of daily PINE_FLOAT balance. X = date, Y = ₹. Negative = "we're floating cash."
2. **Exceptions table** — sortable table of recon failures with status badges.

Header shows trial balance summary (4 accounts + "balanced ✓").

No other pages. No login, no settings, no merchant management.

---

## Data model

```
transactions
  id            INT PK
  merchant_id   TEXT
  amount_paise  INT
  fee_paise     INT
  status        TEXT
  created_at    DATETIME
  settled_to_merchant_at  DATETIME NULL

settlements
  id              INT PK
  bank_ref        TEXT
  batch_id        TEXT
  net_amount_paise INT
  value_date      DATETIME

settlement_lines
  id              INT PK
  settlement_id   INT FK → settlements
  claimed_txn_ref TEXT
  gross_paise     INT
  fee_paise       INT

ledger_entries
  id          INT PK
  event_id    TEXT
  account     TEXT
  amount_paise INT          -- signed: +debit, -credit
  created_at  DATETIME

recon_results
  id                  INT PK
  txn_id              INT FK → transactions NULL
  settlement_line_id  INT FK → settlement_lines NULL
  status              TEXT
  note                TEXT
```

## API surface

| Method | Path | What |
|---|---|---|
| POST | /generate | Run synthetic generator, populate DB |
| POST | /settlements/ingest | Upload messy CSV → parse → settlements + lines |
| POST | /recon/run | Match txns ↔ lines → recon_results + ledger entries |
| GET | /recon/exceptions | Non-MATCHED results |
| GET | /float/daily | Daily PINE_FLOAT balance |
| GET | /ledger/balance | Trial balance (4 accounts + total) |

## Tech stack
- **Backend:** Python 3.9+ / FastAPI / SQLAlchemy / SQLite
- **Frontend:** Next.js / Recharts (float curve) / one page
- **Tests:** pytest (ledger invariant + recon correctness)
- **Deploy:** Render or Railway free tier

## Build order
1. ✅ Ledger core + invariant test + integer money
2. Synthetic generator (messy CSV + txns)
3. Recon engine (many-to-one hero case)
4. Float + exceptions + balance endpoints
5. Dashboard (float curve + exceptions table)
6. README + deploy + Loom + LinkedIn outreach

## Distribution plan
- Deploy live on Render/Railway (clickable URL)
- Record 90-sec Loom walking the float curve + exceptions
- LinkedIn DM 2-3 Pine Labs engineers: "I built a toy version of your settlement-timing problem — 90 sec here."
- README frames as modeled scenario, not their disclosed data
