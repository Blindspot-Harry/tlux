import os
import sqlite3
import bcrypt
from datetime import datetime

DB_FILE = "T-LUX.db"

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@tlux.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
TECH_EMAIL = os.getenv("TECH_EMAIL", "tech@tlux.com")
TECH_PASSWORD = os.getenv("TECH_PASSWORD", "tech123")

# -----------------------
# Definição de tabelas
# -----------------------
tabelas = {
    "users": """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            language TEXT,
            access_key TEXT,
            access_expiry TEXT,
            is_admin INTEGER DEFAULT 0,
            region TEXT DEFAULT 'USD',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    """,
    # ... (resto das tabelas igual à versão anterior)
}

# -----------------------
# Colunas retroativas
# -----------------------
alteracoes = [
    ("users", "password_hash TEXT"),
    ("users", "is_admin INTEGER DEFAULT 0"),
    ("users", "region TEXT DEFAULT 'USD'"),
    ("users", "first_name TEXT"),
    ("users", "last_name TEXT"),
    ("users", "username TEXT"),
    ("users", "updated_at TEXT"),
    ("transactions", "tx_ref TEXT"),
    ("transactions", "stripe_id TEXT"),
    ("transactions", "updated_at TEXT"),
    ("transactions", "imei TEXT"),
    ("transactions", "order_id TEXT"),
    ("transactions", "preco_fornecedor REAL DEFAULT 0.0"),
    ("transactions", "lucro REAL DEFAULT 0.0"),
    ("transactions", "processed INTEGER DEFAULT 0"),
]

indices = [
    "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(user_email)",
    "CREATE INDEX IF NOT EXISTS idx_orders_ref ON orders(order_ref)",
    "CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email)",
    "CREATE INDEX IF NOT EXISTS idx_blocked_users_email ON blocked_users(email)"
]

def migrate():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    print("🔄 Verificando tabelas...")
    for nome, ddl in tabelas.items():
        c.execute(ddl)
        print(f"[OK] Tabela garantida: {nome}")

    print("\n🔄 Verificando colunas...")
    for tabela, coluna in alteracoes:
        try:
            c.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna}")
            print(f"[OK] Adicionada coluna '{coluna}' em {tabela}")
        except sqlite3.OperationalError:
            print(f"[SKIP] Coluna já existe: {tabela}.{coluna}")

    print("\n🔄 Criando índices...")
    for idx in indices:
        c.execute(idx)
    print("[OK] Índices verificados/criados.")

    print("\n🔄 Inserindo usuários iniciais...")
    usuarios_iniciais = [
        (ADMIN_EMAIL, ADMIN_PASSWORD, 1),
        (TECH_EMAIL, TECH_PASSWORD, 0),
    ]
    for email, senha, is_admin in usuarios_iniciais:
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        if c.fetchone() is None:
            pw_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
            c.execute(
                "INSERT INTO users (email, password_hash, is_admin, region, created_at) VALUES (?, ?, ?, ?, ?)",
                (email, pw_hash, is_admin, "USD", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            print(f"[OK] Usuário criado: {email}")
        else:
            print(f"[SKIP] Usuário já existe: {email}")

    conn.commit()
    conn.close()
    print("\n✅ Migração concluída com sucesso!")

if __name__ == "__main__":
    migrate()
