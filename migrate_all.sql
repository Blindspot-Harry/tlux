-- =======================
-- MIGRATION FILE FOR T-LUX DATABASE
-- Version: 2025-10
-- =======================

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT,
    last_name TEXT,
    username TEXT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    language TEXT,
    access_key TEXT,
    access_expiry TEXT,
    is_admin INTEGER DEFAULT 0,
    region TEXT DEFAULT 'USD',
    email_verified INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    purpose TEXT,
    pacote TEXT,
    modelo TEXT,
    imei TEXT,
    sem_sinal INTEGER DEFAULT 0,
    amount REAL,
    status TEXT,
    processed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    order_id TEXT,
    preco_fornecedor REAL DEFAULT 0.0,
    lucro REAL DEFAULT 0.0,
    tx_ref TEXT UNIQUE,
    stripe_id TEXT,
    updated_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    license_key TEXT,
    pacote TEXT,
    modelo TEXT,
    issued_at TEXT,
    expires_at TEXT,
    status TEXT DEFAULT 'active',
    tx_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(tx_id) REFERENCES transactions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    ip_address TEXT,
    status TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS blocked_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    ip_address TEXT,
    blocked_until TEXT,
    UNIQUE(email, ip_address)
);

CREATE TABLE IF NOT EXISTS logs_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    mensagem TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS logs_desbloqueio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_id INTEGER,
    user_email TEXT,
    imei TEXT,
    modelo TEXT,
    status TEXT,
    data_hora TEXT
);

CREATE TABLE IF NOT EXISTS tech_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT,
    mensagem TEXT,
    status TEXT DEFAULT 'open',
    criado_em TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    credit REAL,
    group_name TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT NOT NULL,
    service_id INTEGER NOT NULL,
    service_name TEXT NOT NULL,
    order_ref TEXT UNIQUE,
    imei TEXT,
    status TEXT DEFAULT 'PENDING',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
