"""Synthetic data generator: 1000 txns over 30 days + messy bank settlement CSV.

Mess types (per PRD):
- Netted batches: ~40% of settlements bundle 5-15 txns into 1 deposit
- Fee deduction: 100% — MDR 1.5-2% + GST 18% on MDR
- Missing: ~2% of txns have no settlement line
- Duplicate: ~1% of txns appear twice in settlement
- T+2/T+3 delay: all settlements delayed 2-3 business days
"""
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import Transaction
from app.ledger import record_merchant_payout

DATA_DIR = Path(__file__).parent.parent / "data"
MERCHANTS = [f"MERCH_{i:03d}" for i in range(1, 21)]
MDR_RANGE = (0.015, 0.02)
GST_ON_MDR = 0.18


def _random_amount_paise() -> int:
    return random.randint(20000, 5000000)


def _calc_fee_paise(amount_paise: int, mdr_rate: float) -> int:
    mdr = int(amount_paise * mdr_rate)
    gst = int(mdr * GST_ON_MDR)
    return mdr + gst


def _add_business_days(d: datetime, days: int) -> datetime:
    current = d
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def generate_transactions(db: Session, base_date: datetime, count: int = 1000) -> list:
    txns = []
    for i in range(count):
        day_offset = random.randint(0, 29)
        hour = random.randint(8, 22)
        created = base_date + timedelta(days=day_offset, hours=hour, minutes=random.randint(0, 59))
        amount = _random_amount_paise()
        mdr_rate = random.uniform(*MDR_RANGE)
        fee = _calc_fee_paise(amount, mdr_rate)
        settled_at = _add_business_days(created, 1)

        txn = Transaction(
            merchant_id=random.choice(MERCHANTS),
            amount_paise=amount,
            fee_paise=fee,
            status="captured",
            created_at=created,
            settled_to_merchant_at=settled_at,
        )
        db.add(txn)
        db.flush()

        record_merchant_payout(db, f"payout-{txn.id}", amount, fee)
        txns.append(txn)

    db.commit()
    return txns


def generate_settlement_csv(txns: list, output_path: Path) -> Path:
    random.shuffle(txns)

    lines_to_write = []
    batch_counter = 0
    i = 0

    while i < len(txns):
        txn = txns[i]

        if random.random() < 0.02:
            i += 1
            continue

        if random.random() < 0.40 and i + 5 <= len(txns):
            batch_size = min(random.randint(5, 15), len(txns) - i)
            batch_counter += 1
            batch_id = f"BATCH-{batch_counter:04d}"
            bank_ref = f"UTR-{random.randint(100000000, 999999999)}"
            earliest = min(txns[i:i + batch_size], key=lambda t: t.created_at)
            delay = random.choice([2, 3])
            value_date = _add_business_days(earliest.created_at, delay)

            for j in range(batch_size):
                t = txns[i + j]
                gross = t.amount_paise
                fee = t.fee_paise

                dup = random.random() < 0.01
                if random.random() < 0.03:
                    fee = fee + random.choice([-random.randint(100, 500), random.randint(100, 500)])
                    fee = max(0, fee)

                lines_to_write.append((batch_id, bank_ref, str(t.id), gross, fee, value_date))
                if dup:
                    lines_to_write.append((batch_id, bank_ref, str(t.id), gross, fee, value_date))

            i += batch_size
        else:
            batch_counter += 1
            batch_id = f"BATCH-{batch_counter:04d}"
            bank_ref = f"UTR-{random.randint(100000000, 999999999)}"
            delay = random.choice([2, 3])
            value_date = _add_business_days(txn.created_at, delay)
            gross = txn.amount_paise
            fee = txn.fee_paise

            if random.random() < 0.03:
                fee = fee + random.choice([-random.randint(100, 500), random.randint(100, 500)])
                fee = max(0, fee)

            lines_to_write.append((batch_id, bank_ref, str(txn.id), gross, fee, value_date))

            if random.random() < 0.01:
                lines_to_write.append((batch_id, bank_ref, str(txn.id), gross, fee, value_date))

            i += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["batch_id", "bank_ref", "txn_ref", "gross_paise", "fee_paise", "net_paise", "value_date"])
        for batch_id, bank_ref, txn_ref, gross, fee, vdate in lines_to_write:
            net = gross - fee
            writer.writerow([batch_id, bank_ref, txn_ref, gross, fee, net, vdate.strftime("%Y-%m-%d")])

    return output_path


def run(seed: int = 42):
    random.seed(seed)
    init_db()
    db = SessionLocal()
    base_date = datetime(2026, 1, 1, 0, 0, 0)

    txns = generate_transactions(db, base_date, count=1000)

    txn_data = [
        {
            "id": t.id,
            "merchant_id": t.merchant_id,
            "amount_paise": t.amount_paise,
            "fee_paise": t.fee_paise,
            "created_at": t.created_at.isoformat(),
            "settled_to_merchant_at": t.settled_to_merchant_at.isoformat(),
        }
        for t in txns
    ]
    txn_path = DATA_DIR / "transactions.json"
    txn_path.parent.mkdir(parents=True, exist_ok=True)
    with open(txn_path, "w") as f:
        json.dump(txn_data, f, indent=2)

    csv_path = generate_settlement_csv(txns, DATA_DIR / "settlements.csv")
    return len(txns), csv_path


if __name__ == "__main__":
    count, path = run()
    print(f"Generated {count} txns + settlement CSV at {path}")
