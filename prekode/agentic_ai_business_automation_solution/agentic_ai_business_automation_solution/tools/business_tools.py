import sqlite3, json, uuid
from datetime import datetime
from pathlib import Path

DB=Path(__file__).parents[1]/"data"/"nordictech.db"

def con():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def get_customer(customer_id=None,email=None):
    c=con()
    if customer_id:
        row=c.execute("SELECT * FROM customers WHERE customer_id=?",(customer_id,)).fetchone()
    elif email:
        row=c.execute("SELECT * FROM customers WHERE email=?",(email,)).fetchone()
    else: row=None
    c.close()
    return dict(row) if row else None

def find_customer_by_name(name):
    c=con(); rows=c.execute("SELECT * FROM customers WHERE lower(name) LIKE ?",("%"+name.lower()+"%",)).fetchall(); c.close()
    return [dict(r) for r in rows]

def get_orders(customer_id):
    c=con()
    rows=c.execute("""
    SELECT o.*, p.name AS product_name, p.price_eur, p.stock
    FROM orders o JOIN products p ON p.product_id=o.product_id
    WHERE o.customer_id=? ORDER BY o.order_date DESC
    """,(customer_id,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_order(order_id):
    c=con()
    row=c.execute("""
    SELECT o.*, p.name AS product_name, p.price_eur, p.stock
    FROM orders o JOIN products p ON p.product_id=o.product_id
    WHERE o.order_id=?
    """,(order_id,)).fetchone()
    c.close()
    return dict(row) if row else None

def check_inventory(product_id):
    c=con(); row=c.execute("SELECT * FROM products WHERE product_id=?",(product_id,)).fetchone(); c.close()
    return dict(row) if row else None

def create_ticket(customer_id, order_id, category, description):
    c=con()
    ticket_id="T"+str(uuid.uuid4())[:8].upper()
    c.execute("INSERT INTO support_tickets VALUES (?,?,?,?,?,?)",
              (ticket_id,customer_id,order_id,category,"open",description))
    c.commit(); c.close()
    return {"ticket_id":ticket_id,"status":"open"}

def create_replacement(order_id, customer_id, product_id, approved_by="SYSTEM"):
    c=con()
    rid="R"+str(uuid.uuid4())[:8].upper()
    now=datetime.utcnow().isoformat()
    c.execute("INSERT INTO replacement_actions VALUES (?,?,?,?,?,?,?)",
              (rid,order_id,customer_id,product_id,"CREATED",approved_by,now))
    c.execute("UPDATE products SET stock=stock-1 WHERE product_id=? AND stock>0",(product_id,))
    c.commit(); c.close()
    return {"replacement_id":rid,"status":"CREATED","approved_by":approved_by}

def log_audit(customer_id, action, decision, details):
    c=con()
    c.execute("INSERT INTO audit_log(timestamp,customer_id,action,decision,details) VALUES (?,?,?,?,?)",
              (datetime.utcnow().isoformat(),customer_id,action,decision,json.dumps(details)))
    c.commit(); c.close()

def recent_audit(limit=20):
    c=con(); rows=c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",(limit,)).fetchall(); c.close()
    return [dict(r) for r in rows]
