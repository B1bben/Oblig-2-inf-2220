from pathlib import Path
import sqlite3, json

ROOT=Path(__file__).parent
DB=ROOT/"data"/"nordictech.db"

def test_database():
    assert DB.exists(), "Run scripts_init.py first"
    c=sqlite3.connect(DB)
    n=c.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    c.close()
    assert n>=5

def test_cases():
    cases=json.loads((ROOT/"evaluation/test_cases.json").read_text())
    assert len(cases)>=50
