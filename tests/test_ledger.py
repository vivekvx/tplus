"""The one test that matters: money is conserved, ledger always balances to zero.
Also proves the float gap: between merchant payout and bank settlement, PINE_FLOAT
is negative (we floated our own cash) — the Pine Labs cash-flow story, in numbers.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.ledger import (post, assert_balanced, account_balance,
                        record_merchant_payout, record_bank_settlement)


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_balanced_event_posts():
    db = _session()
    post(db, "e1", [("PINE_FLOAT", -1000), ("MERCHANT_PAYABLE", 1000)])
    assert_balanced(db)


def test_unbalanced_event_rejected():
    db = _session()
    try:
        post(db, "bad", [("PINE_FLOAT", -1000), ("MERCHANT_PAYABLE", 999)])
        assert False, "should have raised"
    except ValueError as e:
        assert "unbalanced" in str(e)


def test_float_gap_then_close():
    """₹1000 sale, ₹20 fee. Pay merchant early, bank settles later."""
    db = _session()
    record_merchant_payout(db, "txn-1", amount_paise=100000, fee_paise=2000)
    assert_balanced(db)
    # we floated net 98000 paise out, bank still owes gross 100000
    assert account_balance(db, "PINE_FLOAT") == -98000
    assert account_balance(db, "BANK_RECEIVABLE") == 100000

    # bank settles T+2: sends net 98000, kept 2000 fee
    record_bank_settlement(db, "txn-1", net_received_paise=98000, fee_deducted_paise=2000)
    assert_balanced(db)
    # receivable cleared, float back to zero, fee nets to zero (we kept none, bank did)
    assert account_balance(db, "BANK_RECEIVABLE") == 0
    assert account_balance(db, "PINE_FLOAT") == 0
