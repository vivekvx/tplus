"""Recon engine tests. Covers the hero case: many-to-one batch un-bundling,
plus all 5 exception statuses + ledger invariant after full recon.
"""
import csv
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Transaction, ReconResult
from app.ledger import record_merchant_payout, assert_balanced, account_balance
from app.recon import ingest_csv, run_recon


def _setup():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _make_txn(db, txn_id, amount_paise, fee_paise, day=5):
    txn = Transaction(
        id=txn_id,
        merchant_id="MERCH_001",
        amount_paise=amount_paise,
        fee_paise=fee_paise,
        status="captured",
        created_at=datetime(2026, 1, day, 10, 0),
        settled_to_merchant_at=datetime(2026, 1, day + 1, 10, 0),
    )
    db.add(txn)
    db.flush()
    record_merchant_payout(db, f"payout-{txn.id}", amount_paise, fee_paise)
    return txn


def _write_csv(rows):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
    writer = csv.writer(tmp)
    writer.writerow(["batch_id", "bank_ref", "txn_ref", "gross_paise", "fee_paise", "net_paise", "value_date"])
    for row in rows:
        gross, fee = row[2], row[3]
        net = gross - fee
        writer.writerow([row[0], "UTR-TEST", row[1], gross, fee, net, "2026-01-08"])
    tmp.close()
    return Path(tmp.name)


def test_hero_many_to_one_batch():
    """10 txns in 1 batch = the Pine Labs hero case."""
    db = _setup()
    for i in range(1, 11):
        _make_txn(db, i, amount_paise=100000, fee_paise=2000)
    db.commit()

    rows = [("BATCH-001", str(i), 100000, 2000) for i in range(1, 11)]
    csv_path = _write_csv(rows)

    ingest_csv(db, csv_path)
    counts = run_recon(db)

    assert counts["MATCHED"] == 10
    assert_balanced(db)
    assert account_balance(db, "BANK_RECEIVABLE") == 0
    assert account_balance(db, "PINE_FLOAT") == 0


def test_missing_txn():
    db = _setup()
    _make_txn(db, 1, 100000, 2000)
    _make_txn(db, 2, 200000, 4000)
    db.commit()

    csv_path = _write_csv([("BATCH-001", "1", 100000, 2000)])
    ingest_csv(db, csv_path)
    counts = run_recon(db)

    assert counts["MATCHED"] == 1
    assert counts["MISSING"] == 1
    assert_balanced(db)


def test_duplicate_detection():
    db = _setup()
    _make_txn(db, 1, 100000, 2000)
    db.commit()

    csv_path = _write_csv([
        ("BATCH-001", "1", 100000, 2000),
        ("BATCH-001", "1", 100000, 2000),
    ])
    ingest_csv(db, csv_path)
    counts = run_recon(db)

    assert counts["MATCHED"] == 1
    assert counts["DUPLICATE"] == 1
    assert_balanced(db)


def test_amount_mismatch():
    db = _setup()
    _make_txn(db, 1, 100000, 2000)
    db.commit()

    csv_path = _write_csv([("BATCH-001", "1", 99000, 2000)])
    ingest_csv(db, csv_path)
    counts = run_recon(db)

    assert counts["AMOUNT_MISMATCH"] == 1
    assert_balanced(db)


def test_fee_drift():
    db = _setup()
    _make_txn(db, 1, 100000, 2000)
    db.commit()

    csv_path = _write_csv([("BATCH-001", "1", 100000, 1800)])
    ingest_csv(db, csv_path)
    counts = run_recon(db)

    assert counts["FEE_DRIFT"] == 1
    assert_balanced(db)
    assert account_balance(db, "BANK_RECEIVABLE") == 0


def test_full_mix():
    """All statuses in one run."""
    db = _setup()
    _make_txn(db, 1, 100000, 2000)
    _make_txn(db, 2, 200000, 4000)
    _make_txn(db, 3, 300000, 6000)
    _make_txn(db, 4, 400000, 8000)
    _make_txn(db, 5, 500000, 10000)
    db.commit()

    csv_path = _write_csv([
        ("BATCH-001", "1", 100000, 2000),
        ("BATCH-001", "3", 299000, 6000),
        ("BATCH-001", "4", 400000, 7500),
        ("BATCH-001", "5", 500000, 10000),
        ("BATCH-001", "5", 500000, 10000),
    ])
    ingest_csv(db, csv_path)
    counts = run_recon(db)

    assert counts.get("MATCHED", 0) == 2
    assert counts.get("MISSING", 0) == 1
    assert counts.get("AMOUNT_MISMATCH", 0) == 1
    assert counts.get("FEE_DRIFT", 0) == 1
    assert counts.get("DUPLICATE", 0) == 1
    assert_balanced(db)
