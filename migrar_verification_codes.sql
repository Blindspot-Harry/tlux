ALTER TABLE verification_codes RENAME TO verification_codes_old;

CREATE TABLE verification_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    email TEXT,
    code_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    attempts INTEGER DEFAULT 0,
    used INTEGER DEFAULT 0,
    last_sent_at TIMESTAMP
);

INSERT INTO verification_codes (user_id, email, created_at, expires_at, used)
SELECT user_id, email, created_at, expires_at, used FROM verification_codes_old;

DROP TABLE verification_codes_old;
