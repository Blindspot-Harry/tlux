# ============================================
# 🧱 fix_tables.py — Reconstrutor completo T-Lux
# ============================================
import sqlite3

DB_PATH = "t-lux.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

print("🔧 [T-LUX] Verificando e criando tabelas essenciais...")

# USERS
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT,
    last_name TEXT,
    username TEXT UNIQUE,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    email_verified INTEGER DEFAULT 0,
    region TEXT DEFAULT 'USD',
    language TEXT DEFAULT 'en',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);
""")

# VERIFICATION CODES
c.execute("""
CREATE TABLE IF NOT EXISTS verification_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    email TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    used INTEGER DEFAULT 0
);
""")

# BLOCKED USERS
c.execute("""
CREATE TABLE IF NOT EXISTS blocked_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    ip_address TEXT,
    blocked_until TEXT
);
""")

# LOGIN ATTEMPTS
c.execute("""
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    ip_address TEXT,
    status TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
""")

# TRANSACTIONS
c.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    tx_ref TEXT,
    stripe_id TEXT,
    amount REAL DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    status TEXT DEFAULT 'pending',
    imei TEXT,
    order_id TEXT,
    preco_fornecedor REAL DEFAULT 0.0,
    lucro REAL DEFAULT 0.0,
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);
""")

# LOGS
c.execute("""
CREATE TABLE IF NOT EXISTS logs_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    tipo TEXT,
    descricao TEXT,
    criado_em TEXT DEFAULT CURRENT_TIMESTAMP
);
""")

conn.commit()
conn.close()
print("✅ [T-LUX] Todas as tabelas foram criadas/verificadas com sucesso!")
