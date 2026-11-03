import sqlite3, csv
from pathlib import Path

ROOT=Path(__file__).parent
DB=ROOT/"data"/"nordictech.db"

TABLES = {
"customers": ("customer_id TEXT PRIMARY KEY, name TEXT, email TEXT, country TEXT, vip INTEGER"),
"products": ("product_id TEXT PRIMARY KEY, name TEXT, category TEXT, price_eur REAL, stock INTEGER"),
"orders": ("order_id TEXT PRIMARY KEY, customer_id TEXT, product_id TEXT, order_date TEXT, status TEXT, delivered_date TEXT, quantity INTEGER"),
"support_tickets": ("ticket_id TEXT PRIMARY KEY, customer_id TEXT, order_id TEXT, category TEXT, status TEXT, description TEXT"),
"employees": ("employee_id TEXT PRIMARY KEY, name TEXT, role TEXT"),
"invoices": ("invoice_id TEXT PRIMARY KEY, customer_id TEXT, order_id TEXT, amount_eur REAL, status TEXT"),
"audit_log": ("id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, customer_id TEXT, action TEXT, decision TEXT, details TEXT"),
"replacement_actions": ("replacement_id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT, product_id TEXT, status TEXT, approved_by TEXT, created_at TEXT")
}

def main():
    if DB.exists():
        DB.unlink()
    con=sqlite3.connect(DB)
    cur=con.cursor()
    for table, schema in TABLES.items():
        cur.execute(f"CREATE TABLE {table} ({schema})")
    for table in ["customers","products","orders","support_tickets","employees","invoices"]:
        path=ROOT/"data"/f"{table}.csv"
        with open(path, newline="", encoding="utf-8") as f:
            rows=list(csv.reader(f)); header=rows[0]; data=rows[1:]
        marks=",".join(["?"]*len(header))
        cur.executemany(f"INSERT INTO {table} ({','.join(header)}) VALUES ({marks})", data)
    con.commit(); con.close()
    print(f"Created {DB}")

if __name__=="__main__":
    main()
