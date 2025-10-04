import sqlite3

DB_FILE = "t-lux.db"

MIGRATIONS = {
    "users": ["email_verified"],
    "transactions": ["sem_sinal", "preco_fornecedor", "lucro", "updated_at"],
    "licenses": ["status"],
    "email_verifications": ["expires_at"],
}

with sqlite3.connect(DB_FILE) as conn:
    c = conn.cursor()
    for table, cols in MIGRATIONS.items():
        c.execute(f"PRAGMA table_info({table})")
        existing = [row[1] for row in c.fetchall()]
        for col in cols:
            if col not in existing:
                if table == "users" and col == "email_verified":
                    c.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
                elif table == "transactions":
                    if col == "sem_sinal":
                        c.execute("ALTER TABLE transactions ADD COLUMN sem_sinal INTEGER DEFAULT 0")
                    elif col == "preco_fornecedor":
                        c.execute("ALTER TABLE transactions ADD COLUMN preco_fornecedor REAL DEFAULT 0.0")
                    elif col == "lucro":
                        c.execute("ALTER TABLE transactions ADD COLUMN lucro REAL DEFAULT 0.0")
                    elif col == "updated_at":
                        c.execute("ALTER TABLE transactions ADD COLUMN updated_at TEXT")
                elif table == "licenses" and col == "status":
                    c.execute("ALTER TABLE licenses ADD COLUMN status TEXT DEFAULT 'active'")
                elif table == "email_verifications" and col == "expires_at":
                    c.execute("ALTER TABLE email_verifications ADD COLUMN expires_at TEXT")
    conn.commit()

print("Migração concluída ✅")
