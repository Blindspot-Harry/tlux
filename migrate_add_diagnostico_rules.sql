-- migrate_add_diagnosis_rules.sql
CREATE TABLE IF NOT EXISTS diagnosis_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,           -- "iPad MDM", "Mac T2 EFI", "Apple Watch FMI", ...
  device_family TEXT,           -- 'iPad','Mac','Watch','Unknown'
  condition_json JSON NOT NULL, -- ex: {"mdm": true, "signal": "no", "chip": "T2"}
  recommended_service_id TEXT,  -- service_id do fornecedor (string)
  provider TEXT DEFAULT 'dhrU_iremove',
  priority INTEGER DEFAULT 100, -- menor = maior prioridade
  active INTEGER DEFAULT 1
);
