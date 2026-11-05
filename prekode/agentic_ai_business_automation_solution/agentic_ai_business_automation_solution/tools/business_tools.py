import sqlite3, json, uuid
from datetime import datetime
from pathlib import Path
import os
from datetime import date
from agent.faults import fault_active

DB = Path(__file__).parents[1] / "data" / "nordictech.db"


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def get_customer(customer_id=None, email=None):
    c = con()
    if customer_id:
        row = c.execute(
            "SELECT * FROM customers WHERE customer_id=?", (customer_id,)
        ).fetchone()
    elif email:
        row = c.execute("SELECT * FROM customers WHERE email=?", (email,)).fetchone()
    else:
        row = None
    c.close()
    return dict(row) if row else None


def find_customer_by_name(name):
    c = con()
    rows = c.execute(
        "SELECT * FROM customers WHERE lower(name) LIKE ?", ("%" + name.lower() + "%",)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_orders(customer_id):
    c = con()
    rows = c.execute(
        """
    SELECT o.*, p.name AS product_name, p.price_eur, p.stock
    FROM orders o JOIN products p ON p.product_id=o.product_id
    WHERE o.customer_id=? ORDER BY o.order_date DESC
    """,
        (customer_id,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_order(order_id):
    c = con()
    row = c.execute(
        """
    SELECT o.*, p.name AS product_name, p.price_eur, p.stock
    FROM orders o JOIN products p ON p.product_id=o.product_id
    WHERE o.order_id=?
    """,
        (order_id,),
    ).fetchone()
    c.close()
    return dict(row) if row else None


def check_inventory(product_id):
    c = con()
    row = c.execute(
        "SELECT * FROM products WHERE product_id=?", (product_id,)
    ).fetchone()
    c.close()
    return dict(row) if row else None


def create_ticket(customer_id, order_id, category, description):
    c = con()
    ticket_id = "T" + str(uuid.uuid4())[:8].upper()
    c.execute(
        "INSERT INTO support_tickets VALUES (?,?,?,?,?,?)",
        (ticket_id, customer_id, order_id, category, "open", description),
    )
    c.commit()
    c.close()
    return {"ticket_id": ticket_id, "status": "open"}


def create_replacement(order_id, customer_id, product_id, approved_by="SYSTEM"):
    c = con()
    rid = "R" + str(uuid.uuid4())[:8].upper()
    now = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO replacement_actions VALUES (?,?,?,?,?,?,?)",
        (rid, order_id, customer_id, product_id, "CREATED", approved_by, now),
    )
    c.execute(
        "UPDATE products SET stock=stock-1 WHERE product_id=? AND stock>0",
        (product_id,),
    )
    c.commit()
    c.close()
    return {"replacement_id": rid, "status": "CREATED", "approved_by": approved_by}


def log_audit(customer_id, action, decision, details):
    c = con()
    c.execute(
        "INSERT INTO audit_log(timestamp,customer_id,action,decision,details) VALUES (?,?,?,?,?)",
        (
            datetime.utcnow().isoformat(),
            customer_id,
            action,
            decision,
            json.dumps(details),
        ),
    )
    c.commit()
    c.close()


def recent_audit(limit=20):
    c = con()
    rows = c.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


REFUND_AUTO_LIMIT_EUR = 200
RETURN_WINDOW_DAYS = 30


def _today():
    return date.fromisoformat(os.getenv("REFUND_TODAY", "2026-09-20"))


def get_invoice(order_id):
    c = con()
    row = c.execute("SELECT * FROM invoices WHERE order_id=?", (order_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def check_refund_eligibility(invoice, order):
    def no(reason, route="TICKET"):
        return {"eligible": False, "reason": reason, "route": route}

    if not invoice:
        return no("No invoice found for this order.")
    if invoice["customer_id"] != order["customer_id"]:
        return no("Invoice does not belong to this customer.", "ESCALATE")
    if invoice["status"] == "refunded":
        return no("Invoice has already been refunded.")
    if invoice["status"] != "paid":
        return no(f"Invoice status is '{invoice['status']}', not paid.")
    if order["status"] != "delivered":
        return no("Order is not delivered; refund requires review.", "ESCALATE")
    days = (_today() - date.fromisoformat(order["delivered_date"])).days
    if days > RETURN_WINDOW_DAYS:
        return no(
            f"Delivered {days} days ago; outside the {RETURN_WINDOW_DAYS}-day window.",
            "ESCALATE",
        )
    return {
        "eligible": True,
        "reason": "Paid, delivered and within return window.",
        "amount_eur": float(invoice["amount_eur"]),
    }


def issue_refund(invoice_id, amount, approved_by):
    if fault_active("db_down"):
        raise sqlite3.OperationalError("injected fault: db_down")
    c = con()
    cur = c.execute(
        "UPDATE invoices SET status='refunded' WHERE invoice_id=? AND status='paid'",
        (invoice_id,),
    )
    if cur.rowcount != 1:
        c.close()
        raise ValueError("Invoice is not refundable")
    rid = "RF" + str(uuid.uuid4())[:8].upper()
    c.execute(
        "INSERT INTO refunds VALUES (?,?,?,?,?)",
        (rid, invoice_id, amount, approved_by, datetime.utcnow().isoformat()),
    )
    c.commit()
    c.close()
    return {
        "refund_id": rid,
        "invoice_id": invoice_id,
        "amount_eur": amount,
        "status": "REFUNDED",
        "approved_by": approved_by,
    }


def generate_invoice_summary(invoice_id):
    c = con()
    row = c.execute(
        "SELECT * FROM invoices WHERE invoice_id=?", (invoice_id,)
    ).fetchone()
    c.close()
    return dict(row) if row else None
