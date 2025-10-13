-- migrate_add_services.sql
CREATE TABLE IF NOT EXISTS services (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,              -- ex: 'dhrU_iremove'
  service_id TEXT NOT NULL,            -- id do fornecedor (string)
  group_name TEXT,
  name TEXT NOT NULL,
  credit REAL,                         -- custo fornecedor (USD)
  currency TEXT DEFAULT 'USD',
  markup_percent REAL DEFAULT 50,      -- tua margem padrão (%)
  retail_price REAL,                   -- preço final calculado
  available INTEGER DEFAULT 1,
  meta JSON,                           -- livre: delivery, notes, required_fields...
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(provider, service_id)
);
