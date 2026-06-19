"""Double-entry ledger core. Every event posts >=2 entries summing to zero.

The whole point of the project: money is never created or destroyed, only moved.
A balanced ledger is the invariant a fintech reviewer will check first.
"""
from datetime import datetime, timezone
from typing import List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import LedgerEntry

# An entry leg: (account, signed_paise). +debit, -credit.
Leg = Tuple[str, int]


def post(db: Session, event_id: str, legs: List[Leg]) -> None:
    """Post a balanced set of legs as one event. Rejects unbalanced events."""
    total = sum(amount for _, amount in legs)
    if total != 0:
        raise ValueError(f"Event '{event_id}' unbalanced by {total} paise: {legs}")
    now = datetime.now(timezone.utc)
    for account, amount in legs:
        db.add(LedgerEntry(event_id=event_id, account=account,
                           amount_paise=amount, created_at=now))
    db.flush()


def ledger_total(db: Session) -> int:
    """SUM of every entry. Must be 0 if the ledger is consistent."""
    return db.query(func.coalesce(func.sum(LedgerEntry.amount_paise), 0)).scalar()


def account_balance(db: Session, account: str) -> int:
    return db.query(func.coalesce(func.sum(LedgerEntry.amount_paise), 0)).filter(
        LedgerEntry.account == account).scalar()


def assert_balanced(db: Session) -> None:
    """The invariant. Call after every mutation."""
    total = ledger_total(db)
    if total != 0:
        raise ValueError(f"Ledger unbalanced by {total} paise")


# --- domain events: each records the two-clock settlement story ---

def record_merchant_payout(db: Session, event_id: str, amount_paise: int, fee_paise: int) -> None:
    """We pay merchant early (T+1). Net leaves float; fee booked as income.
    Bank still owes us the gross (BANK_RECEIVABLE) — collected later at T+2/T+3."""
    net = amount_paise - fee_paise
    post(db, event_id, [
        ("PINE_FLOAT", -net),          # cash out the door to merchant
        ("FEE_INCOME", -fee_paise),    # our fee (credit = income)
        ("BANK_RECEIVABLE", amount_paise),  # bank owes us the gross (debit asset)
    ])


def record_bank_settlement(db: Session, event_id: str, net_received_paise: int,
                           fee_deducted_paise: int) -> None:
    """Bank finally pays us (T+2/T+3). Clears receivable, cash returns to float."""
    gross = net_received_paise + fee_deducted_paise
    post(db, event_id, [
        ("BANK_RECEIVABLE", -gross),       # receivable cleared (credit asset)
        ("PINE_FLOAT", net_received_paise),  # cash back into float
        ("FEE_INCOME", fee_deducted_paise),  # bank kept fee (re-debits the income we credited)
    ])
