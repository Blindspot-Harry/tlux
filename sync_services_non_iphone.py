#!/usr/bin/env python3
import os, sqlite3, json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "t-lux.db")

# grupos/padrões que vamos EXCLUIR (iPhone), o resto entra na tabela:
EXCLUDE_PATTERNS = [
    "A12+ iCloud Bypass [iPhone]",
    "A12+ iCloud Bypass [iPhone] [NO SIGNAL]",
    "A7+ iCloud Bypass [SIGNAL]",
    "A7 + iCloud Bypass [No Signal]",
]

def should_exclude(group_name: str) -> bool:
    g = (group_name or "").lower()
    if "iphone" in g and "mdm" not in g:
        return True
    for p in EXCLUDE_PATTERNS:
        if p.lower() in g:
            return True
    return False

def calc_retail(credit: float, default_markup=50.0) -> float:
    # regra simples: margem % com piso por faixa (opcional)
    if credit is None:
        return None
    retail = round(credit * (1 + default_markup/100.0), 2)
    # opcional: pisos mínimos
    if credit <= 10 and retail < credit + 5:
        retail = round(credit + 5, 2)
    elif credit <= 50 and retail < credit + 15:
        retail = round(credit + 15, 2)
    elif credit > 50 and retail < credit + 25:
        retail = round(credit + 25, 2)
    return retail

def upsert(conn, row):
    now = datetime.utcnow().isoformat()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO services(provider, service_id, group_name, name, credit, currency, markup_percent, retail_price, meta, available, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
    ON CONFLICT(provider, service_id) DO UPDATE SET
      group_name=excluded.group_name,
      name=excluded.name,
      credit=excluded.credit,
      currency=excluded.currency,
      markup_percent=excluded.markup_percent,
      retail_price=excluded.retail_price,
      meta=excluded.meta,
      available=1,
      updated_at=excluded.updated_at;
    """, (
        row["provider"], row["service_id"], row["group_name"], row["name"],
        row["credit"], row["currency"], row["markup_percent"], row["retail_price"],
        json.dumps(row.get("meta") or {}), now, now
    ))
    conn.commit()

def main():
    # importamos o parser que já SABE ler a resposta da API
    from listar_servicos import get_structured_services

    groups = get_structured_services()
    conn = sqlite3.connect(DB_PATH)
    count = 0
    for g in groups:
        if should_exclude(g["group"]):
            continue
        for s in g["items"]:
            credit = s.get("credit") if s.get("credit") is not None else 0.0
            retail = calc_retail(credit, default_markup=50.0)
            row = {
                "provider": "dhrU_iremove",
                "service_id": str(s["id"]),
                "group_name": g["group"],
                "name": s["name"],
                "credit": credit,
                "currency": s.get("currency", "USD"),
                "markup_percent": 50.0,
                "retail_price": retail,
                "meta": {}
            }
            upsert(conn, row)
            count += 1
    conn.close()
    print(f"✅ sincronizados {count} serviços (não-iPhone)")

if __name__ == "__main__":
    main()
