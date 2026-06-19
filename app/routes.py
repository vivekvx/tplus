"""API endpoints."""
import os
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db import SessionLocal
from app.models import LedgerEntry, ReconResult, Transaction, ACCOUNTS
from app.generator import run as generate_data
from app.recon import ingest_csv, run_recon

router = APIRouter()
DATA_DIR = Path(__file__).parent.parent / "data"

ALLOWED_ORIGINS = os.environ.get("CORS_ORIGINS", "*")


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/generate")
def generate(seed: int = 42):
    from app.db import Base, engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    count, csv_path = generate_data(seed)
    return {"txns_generated": count, "csv_path": str(csv_path)}


@router.post("/settlements/ingest")
def ingest(db: Session = Depends(get_db)):
    csv_path = DATA_DIR / "settlements.csv"
    if not csv_path.exists():
        return {"error": "Run /generate first"}
    lines = ingest_csv(db, csv_path)
    return {"settlement_lines_ingested": len(lines)}


@router.post("/recon/run")
def recon(db: Session = Depends(get_db)):
    counts = run_recon(db)
    return {"recon_results": counts}


@router.get("/recon/exceptions")
def exceptions(db: Session = Depends(get_db)):
    results = db.query(ReconResult).filter(ReconResult.status != "MATCHED").all()
    txn_ids = [r.txn_id for r in results if r.txn_id]
    txn_map = {}
    if txn_ids:
        txns = db.query(Transaction).filter(Transaction.id.in_(txn_ids)).all()
        txn_map = {t.id: t for t in txns}
    out = []
    for r in results:
        amount = None
        if r.txn_id and r.txn_id in txn_map:
            amount = txn_map[r.txn_id].amount_paise
        out.append({
            "id": r.id,
            "txn_id": r.txn_id,
            "settlement_line_id": r.settlement_line_id,
            "status": r.status,
            "amount_paise": amount,
            "amount_display": f"₹{amount / 100:,.2f}" if amount else None,
            "note": r.note,
        })
    return out


@router.get("/float/daily")
def float_daily(db: Session = Depends(get_db)):
    rows = (
        db.query(
            func.date(LedgerEntry.created_at).label("date"),
            func.sum(LedgerEntry.amount_paise).label("delta"),
        )
        .filter(LedgerEntry.account == "PINE_FLOAT")
        .group_by(func.date(LedgerEntry.created_at))
        .order_by(func.date(LedgerEntry.created_at))
        .all()
    )
    result = []
    running = 0
    for date_val, delta in rows:
        running += delta
        result.append({
            "date": str(date_val),
            "float_paise": running,
            "float_display": f"₹{running / 100:,.2f}",
        })
    return result


@router.post("/pipeline")
def full_pipeline(seed: int = 42):
    """One-click: generate → ingest → recon."""
    from app.db import Base, engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    count, csv_path = generate_data(seed)
    db = SessionLocal()
    try:
        lines = ingest_csv(db, csv_path)
        counts = run_recon(db)
        return {"txns": count, "lines": len(lines), "recon": counts}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/ledger/balance")
def trial_balance(db: Session = Depends(get_db)):
    accounts = {}
    for acct in ACCOUNTS:
        bal = db.query(func.coalesce(func.sum(LedgerEntry.amount_paise), 0)).filter(
            LedgerEntry.account == acct).scalar()
        accounts[acct] = bal
    total = sum(accounts.values())
    return {
        "accounts": accounts,
        "total": total,
        "balanced": total == 0,
    }


@router.get("/recon/summary")
def recon_summary(db: Session = Depends(get_db)):
    rows = db.query(ReconResult.status, func.count()).group_by(ReconResult.status).all()
    return {status: count for status, count in rows}
