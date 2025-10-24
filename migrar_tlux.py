# migrar_tlux.py
import sqlite3, os

CANDIDATES = ["t-lux.db", "T-LUX.db", "T-LUX.db.bak2", "t-lux.db.bak2"]
db_path = next((p for p in CANDIDATES if os.path.exists(p)), None)
if not db_path:
    raise SystemExit("❌ No database file found (t-lux.db / T-LUX.db). Run this from project root.")

print(f"[INFO] Using DB: {db_path}")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

def has_col(table, col):
    c.execute(f"PRAGMA table_info({table})")
    return any(r["name"] == col for r in c.fetchall())

def add_col(table, col, decl):
    try:
        if not has_col(table, col):
            print(f"[MIGRATE] Adding column '{col}' → {table} ...")
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            conn.commit()
        else:
            print(f"[OK] Column '{col}' already exists in {table}")
    except Exception as e:
        print(f"[WARN] Failed to add {col} to {table}: {e}")

# ========================
# USERS TABLE
# ========================
add_col("users", "blocked", "INTEGER DEFAULT 0")
add_col("users", "approved", "INTEGER DEFAULT 0")
add_col("users", "role", "TEXT DEFAULT 'user'")
add_col("users", "balance", "REAL DEFAULT 0.0")
add_col("users", "is_admin", "INTEGER DEFAULT 0")
add_col("users", "created_at", "TEXT DEFAULT CURRENT_TIMESTAMP")

# Normalize existing admins
try:
    c.execute("UPDATE users SET approved=1, blocked=0 WHERE is_admin=1")
    conn.commit()
    print("[OK] Existing admins normalized.")
except Exception as e:
    print("[WARN] Could not normalize admins:", e)

# ========================
# TRANSACTIONS TABLE
# ========================
add_col("transactions", "cost_price", "REAL DEFAULT 0.0")
add_col("transactions", "profit", "REAL DEFAULT 0.0")
add_col("transactions", "processed", "INTEGER DEFAULT 0")
add_col("transactions", "imei", "TEXT")
add_col("transactions", "modelo", "TEXT")
add_col("transactions", "status", "TEXT DEFAULT 'pending'")
add_col("transactions", "created_at", "TEXT DEFAULT CURRENT_TIMESTAMP")

# ========================
# LICENSES TABLE
# ========================
add_col("licenses", "expires_at", "TEXT")
add_col("licenses", "issued_at", "TEXT DEFAULT CURRENT_TIMESTAMP")

# ========================
# MESSAGES TABLE
# ========================
try:
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER,
        to_user_id INTEGER,
        content TEXT,
        seen INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("[OK] Ensured messages table exists.")
except Exception as e:
    print("[WARN] Could not ensure messages table:", e)

# ========================
# LOGS TABLE
# ========================
try:
    c.execute("""
    CREATE TABLE IF NOT EXISTS logs_eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        user_email TEXT,
        acao TEXT,
        data_hora TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("[OK] Ensured logs_eventos table exists.")
except Exception as e:
    print("[WARN] Could not ensure logs_eventos:", e)

# ========================
# BALANCE LEDGER TABLE
# ========================
try:
    c.execute("""
    CREATE TABLE IF NOT EXISTS balance_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        change REAL,
        reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("[OK] Ensured balance_ledger table exists.")
except Exception as e:
    print("[WARN] Could not ensure balance_ledger:", e)

# ========================
# SANITY PRINT
# ========================
for table in ["users", "transactions", "licenses", "messages", "logs_eventos", "balance_ledger"]:
    c.execute(f"PRAGMA table_info({table})")
    cols = [r["name"] for r in c.fetchall()]
    print(f"[INFO] {table} columns:", cols)

conn.close()
print("\n✅ Migration completed successfully. All required columns verified.")
