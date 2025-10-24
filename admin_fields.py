# migrate_admin_fields.py
import sqlite3, os

CANDIDATES = ["t-lux.db", "T-LUX.db", "T-LUX.db.bak2", "t-lux.db.bak2"]
db_path = next((p for p in CANDIDATES if os.path.exists(p)), None)
if not db_path:
    raise SystemExit("No database file found (looked for t-lux.db / T-LUX.db). Run this from your project root.")

print(f"[INFO] Using DB: {db_path}")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

def has_col(table, col):
    c.execute(f"PRAGMA table_info({table})")
    return any(r["name"] == col for r in c.fetchall())

def add_col(table, col, decl):
    if not has_col(table, col):
        print(f"[MIGRATE] Adding column {col} to {table} ...")
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        conn.commit()
    else:
        print(f"[OK] Column {col} already exists in {table}")

# users table: blocked, approved, role, balance
add_col("users", "blocked", "INTEGER DEFAULT 0")
add_col("users", "approved", "INTEGER DEFAULT 0")
add_col("users", "role", "TEXT DEFAULT 'user'")
add_col("users", "balance", "REAL DEFAULT 0.0")

# optional normalization for existing admin row(s)
try:
    c.execute("UPDATE users SET approved=1, blocked=0 WHERE is_admin=1")
    conn.commit()
    print("[OK] Ensured existing admins are approved and unblocked.")
except Exception as e:
    print("[WARN] Could not normalize admin flags:", e)

# sanity print
c.execute("PRAGMA table_info(users)")
cols = [r["name"] for r in c.fetchall()]
print("[INFO] users columns:", cols)

conn.close()
print("[DONE] Migration complete.")
