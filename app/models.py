"""ORM models. ALL money is integer paise — never float. ₹1850.50 -> 185050."""
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Transaction(Base):
    """Gateway side: what we processed and paid the merchant (early, T+1)."""
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String, index=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    fee_paise: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="captured")
    created_at: Mapped[datetime] = mapped_column(DateTime)
    settled_to_merchant_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class Settlement(Base):
    """Bank side: one deposit the bank actually sent us (often nets many txns, T+2/T+3)."""
    __tablename__ = "settlements"
    id: Mapped[int] = mapped_column(primary_key=True)
    bank_ref: Mapped[str] = mapped_column(String, index=True)
    batch_id: Mapped[str] = mapped_column(String, index=True)
    net_amount_paise: Mapped[int] = mapped_column(Integer)
    value_date: Mapped[datetime] = mapped_column(DateTime)


class SettlementLine(Base):
    """Un-bundled batch: one claimed txn inside a Settlement (the many-to-one hero case)."""
    __tablename__ = "settlement_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("settlements.id"), index=True)
    claimed_txn_ref: Mapped[str] = mapped_column(String, index=True)
    gross_paise: Mapped[int] = mapped_column(Integer)
    fee_paise: Mapped[int] = mapped_column(Integer, default=0)


class LedgerEntry(Base):
    """Append-only double-entry. Signed paise. SUM over all rows MUST equal 0."""
    __tablename__ = "ledger_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String, index=True)
    account: Mapped[str] = mapped_column(String, index=True)  # see ACCOUNTS below
    amount_paise: Mapped[int] = mapped_column(Integer)  # +debit / -credit
    created_at: Mapped[datetime] = mapped_column(DateTime)


class ReconResult(Base):
    __tablename__ = "recon_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    txn_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    settlement_line_id: Mapped[int] = mapped_column(ForeignKey("settlement_lines.id"), nullable=True)
    status: Mapped[str] = mapped_column(String)  # MATCHED|MISSING|AMOUNT_MISMATCH|DUPLICATE|FEE_DRIFT
    note: Mapped[str] = mapped_column(String, default="")


# Ledger accounts. ponytail: plain strings, not an enum table — 4 fixed accounts.
ACCOUNTS = ("MERCHANT_PAYABLE", "BANK_RECEIVABLE", "PINE_FLOAT", "FEE_INCOME")
