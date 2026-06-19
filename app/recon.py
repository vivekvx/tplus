"""Reconciliation engine: match gateway txns ↔ bank settlement lines.

Hero case: many-to-one (1 bank deposit = N txns netted with fees deducted).
Un-bundles batches, matches per-line, flags exceptions, posts ledger entries.
"""
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from sqlalchemy.orm import Session

from app.models import Transaction, Settlement, SettlementLine, ReconResult
from app.ledger import record_bank_settlement, assert_balanced


def ingest_csv(db: Session, csv_path: Path) -> List[SettlementLine]:
    """Parse messy bank CSV → Settlement + SettlementLine rows.

    Groups CSV rows by batch_id. Each batch = one Settlement (one bank deposit).
    Each row within a batch = one SettlementLine (one claimed txn).
    """
    batches: Dict[str, list] = defaultdict(list)
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            batches[row["batch_id"]].append(row)

    all_lines = []
    for batch_id, rows in batches.items():
        bank_ref = rows[0]["bank_ref"]
        # ponytail: value_date from first row in batch — all rows in a batch share it
        value_date = datetime.strptime(rows[0]["value_date"], "%Y-%m-%d")
        net_total = sum(int(r["net_paise"]) for r in rows)

        settlement = Settlement(
            bank_ref=bank_ref,
            batch_id=batch_id,
            net_amount_paise=net_total,
            value_date=value_date,
        )
        db.add(settlement)
        db.flush()

        for row in rows:
            line = SettlementLine(
                settlement_id=settlement.id,
                claimed_txn_ref=row["txn_ref"],
                gross_paise=int(row["gross_paise"]),
                fee_paise=int(row["fee_paise"]),
            )
            db.add(line)
            db.flush()
            all_lines.append(line)

    db.commit()
    return all_lines


def run_recon(db: Session) -> Dict[str, int]:
    """Match settlement lines to gateway txns. Post ledger entries for matches.

    Returns counts per status: {"MATCHED": N, "MISSING": N, ...}
    """
    txns = {str(t.id): t for t in db.query(Transaction).all()}
    lines = db.query(SettlementLine).all()

    seen_refs: Dict[str, int] = defaultdict(int)
    covered_txn_ids = set()
    counts = defaultdict(int)

    for line in lines:
        ref = line.claimed_txn_ref
        seen_refs[ref] += 1

        if ref not in txns:
            db.add(ReconResult(
                settlement_line_id=line.id,
                status="ORPHAN",
                note=f"Settlement line claims txn_ref={ref} but no such txn exists",
            ))
            counts["ORPHAN"] += 1
            continue

        txn = txns[ref]
        covered_txn_ids.add(ref)

        if seen_refs[ref] > 1:
            db.add(ReconResult(
                txn_id=txn.id,
                settlement_line_id=line.id,
                status="DUPLICATE",
                note=f"txn_ref={ref} claimed by {seen_refs[ref]} settlement lines",
            ))
            counts["DUPLICATE"] += 1
            continue

        if line.gross_paise != txn.amount_paise:
            db.add(ReconResult(
                txn_id=txn.id,
                settlement_line_id=line.id,
                status="AMOUNT_MISMATCH",
                note=f"Expected gross={txn.amount_paise}, got {line.gross_paise}",
            ))
            counts["AMOUNT_MISMATCH"] += 1
            continue

        if line.fee_paise != txn.fee_paise:
            db.add(ReconResult(
                txn_id=txn.id,
                settlement_line_id=line.id,
                status="FEE_DRIFT",
                note=f"Expected fee={txn.fee_paise}, got {line.fee_paise}",
            ))
            counts["FEE_DRIFT"] += 1
            net = line.gross_paise - line.fee_paise
            record_bank_settlement(db, f"settle-{line.id}", net, line.fee_paise)
            continue

        db.add(ReconResult(
            txn_id=txn.id,
            settlement_line_id=line.id,
            status="MATCHED",
            note="",
        ))
        counts["MATCHED"] += 1
        net = line.gross_paise - line.fee_paise
        record_bank_settlement(db, f"settle-{line.id}", net, line.fee_paise)

    for txn_ref, txn in txns.items():
        if txn_ref not in covered_txn_ids:
            db.add(ReconResult(
                txn_id=txn.id,
                status="MISSING",
                note="No settlement line found for this txn",
            ))
            counts["MISSING"] += 1

    db.commit()
    assert_balanced(db)
    return dict(counts)
