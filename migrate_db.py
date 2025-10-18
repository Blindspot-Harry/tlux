# ================================================
# 🧩 migrate_db.py — Migração completa do T-Lux DB
# ================================================
import os
import sqlite3
import bcrypt
from datetime import datetime

DB_FILE = "t-lux.db"

# ==========================================================
# CONFIGURAÇÃO DOS USUÁRIOS INICIAIS (fixo para T-Lux)
# ==========================================================
ADMIN_EMAIL = "arrymauai3@gmail.com"
ADMIN_PASSWORD = "404315"
TECH_EMAIL = "tluxblindspot@gmail.com"
TECH_PASSWORD = "4043115"

# ==========================================================
# TABELAS PRINCIPAIS
# ==========================================================
tabelas = {
    "users": """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            is_admin INTEGER DEFAULT 0,
            email_verified INTEGER DEFAULT 0,
            region TEXT DEFAULT 'USD',
            language TEXT DEFAULT 'en',
            access_key TEXT,
            access_expiry TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    """,
    "transactions": """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tx_ref TEXT,
            stripe_id TEXT,
            amount REAL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'pending',
            imei TEXT,
            modelo TEXT,
            order_id TEXT,
            preco_fornecedor REAL DEFAULT 0.0,
            lucro REAL DEFAULT 0.0,
            processed INTEGER DEFAULT 0,
            purpose TEXT DEFAULT 'unlock',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    """,
    "orders": """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            order_ref TEXT,
            product_name TEXT,
            amount REAL,
            currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "logs_desbloqueio": """
        CREATE TABLE IF NOT EXISTS logs_desbloqueio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            imei TEXT,
            modelo TEXT,
            resultado TEXT,
            fornecedor TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "logs": """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            acao TEXT,
            descricao TEXT,
            ip TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "verification_codes": """
        CREATE TABLE IF NOT EXISTS verification_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            email TEXT NOT NULL,
            code_hash TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT,
            used INTEGER DEFAULT 0
        )
    """,
    "blocked_users": """
        CREATE TABLE IF NOT EXISTS blocked_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            ip_address TEXT,
            blocked_until TEXT
        )
    """,
    "login_attempts": """
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            ip_address TEXT,
            status TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "logs_eventos": """
        CREATE TABLE IF NOT EXISTS logs_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tipo TEXT,
            descricao TEXT,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """
}

# ==========================================================
# COLUNAS EXTRA (retrocompatibilidade)
# ==========================================================
alteracoes = [
    ("users", "email_verified INTEGER DEFAULT 0"),
    ("users", "language TEXT DEFAULT 'en'"),
    ("users", "access_key TEXT"),
    ("users", "access_expiry TEXT"),
    ("transactions", "processed INTEGER DEFAULT 0"),
    ("transactions", "lucro REAL DEFAULT 0.0"),
    ("transactions", "preco_fornecedor REAL DEFAULT 0.0"),
    ("transactions", "imei TEXT"),
    ("transactions", "modelo TEXT"),
    ("transactions", "order_id TEXT"),
    ("transactions", "purpose TEXT DEFAULT 'unlock'")
]

# ==========================================================
# ÍNDICES
# ==========================================================
indices = [
    "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email)",
    "CREATE INDEX IF NOT EXISTS idx_blocked_users_email ON blocked_users(email)"
]

# ==========================================================
# FUNÇÃO PRINCIPAL
# ==========================================================
def migrate():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    print("🔄 Verificando tabelas...")
    for nome, ddl in tabelas.items():
        try:
            c.execute(ddl)
            print(f"[OK] Tabela garantida: {nome}")
        except Exception as e:
            print(f"[ERRO] Falha ao criar {nome}: {e}")

    print("\n🔄 Verificando colunas...")
    for tabela, coluna in alteracoes:
        try:
            c.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna}")
            print(f"[OK] Adicionada coluna '{coluna}' em {tabela}")
        except sqlite3.OperationalError:
            print(f"[SKIP] Coluna já existe: {tabela}.{coluna}")

    print("\n🔄 Criando índices...")
    for idx in indices:
        try:
            c.execute(idx)
        except Exception as e:
            print(f"[ERRO] Falha ao criar índice: {e}")
    print("[OK] Índices verificados/criados.")

    print("\n🔄 Inserindo usuários iniciais...")

    usuarios_iniciais = [
        (ADMIN_EMAIL, ADMIN_PASSWORD, 1, "Administrador"),
        (TECH_EMAIL, TECH_PASSWORD, 0, "Técnico")
    ]

    for email, senha, is_admin, cargo in usuarios_iniciais:
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        if c.fetchone() is None:
            pw_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
            c.execute(
                """
                INSERT INTO users 
                (email, password_hash, is_admin, region, created_at, email_verified, access_expiry)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    email,
                    pw_hash,
                    is_admin,
                    "USD",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "2099-12-31 23:59:59"  # 💎 acesso ilimitado
                ),
            )
            print(f"[OK] {cargo} criado com acesso ilimitado: {email}")
        else:
            print(f"[SKIP] {cargo} já existe: {email}")

    conn.commit()
    conn.close()
    print("\n✅ Migração concluída com sucesso!")

# ==========================================================
# EXECUÇÃO
# ==========================================================
if __name__ == "__main__":
    migrate()
