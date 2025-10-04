-- USERS
ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0;

-- TRANSACTIONS
ALTER TABLE transactions ADD COLUMN sem_sinal INTEGER DEFAULT 0;
ALTER TABLE transactions ADD COLUMN preco_fornecedor REAL DEFAULT 0.0;
ALTER TABLE transactions ADD COLUMN lucro REAL DEFAULT 0.0;
ALTER TABLE transactions ADD COLUMN updated_at TEXT;

-- LICENSES
ALTER TABLE licenses ADD COLUMN status TEXT DEFAULT 'active';

-- EMAIL VERIFICATIONS
ALTER TABLE email_verifications ADD COLUMN expires_at TEXT;

-- ÍNDICES úteis (idempotentes)
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_licenses_user ON licenses(user_id);
CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email);
CREATE INDEX IF NOT EXISTS idx_blocked_users_email ON blocked_users(email);
CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(user_email);
CREATE INDEX IF NOT EXISTS idx_orders_ref ON orders(order_ref);
