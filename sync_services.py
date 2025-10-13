#!/usr/bin/env python3
"""
sync_services.py
Sincroniza serviços DHRU (iRemoval) para a tabela services do DB local.
"""

import os
import sqlite3
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # carrega .env

DB_PATH = os.getenv("DB_PATH", "t-lux.db")
DHRU_API_URL = os.getenv("DHRU_API_URL")
DHRU_API_KEY = os.getenv("DHRU_API_KEY")
DHRU_USERNAME = os.getenv("DHRU_USERNAME", "")

def fetch_services():
    payload = {"api_key": DHRU_API_KEY}
    if DHRU_USERNAME:
        payload["username"] = DHRU_USERNAME
    # dependendo da API, talvez seja preciso enviar 'action' ou 'list' - ajustar conforme listar_servicos.py
    r = requests.post(DHRU_API_URL, data=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def normalize_and_extract(json_response):
    """
    Normaliza a resposta para uma lista de dicts:
    {'service_id': '1', 'group': 'A7+ iCloud Bypass [SIGNAL]', 'name': 'iCloud Bypass for...', 'credit': 10.0}
    """
    services = []
    # A forma exata depende do JSON que a API retorna. Se o listar_servicos.py já parseia bem,
    # podes adaptar o parsing daqui. Exemplo genérico:
    # Assumiremos que a resposta tem algo como: {"SUCCESS": [{"data": [...]}]} ou uma lista agrupada.
    # Aqui vamos tentar detectar estruturas comuns:
    if isinstance(json_response, dict):
        # procurar por chaves with services
        for k,v in json_response.items():
            if isinstance(v, list):
                for item in v:
                    # heurística: se item tem keys id, name, price
                    sid = item.get("id") or item.get("service_id") or item.get("ServiceID")
                    name = item.get("name") or item.get("ServiceName") or item.get("title")
                    credit = item.get("credit") or item.get("price") or item.get("amount")
                    group = item.get("group") or item.get("category")
                    if sid and name:
                        services.append({
                            "service_id": str(sid),
                            "group_name": group or "",
                            "name": name,
                            "credit": float(credit) if credit else None
                        })
    # fallback: if parse fails, return empty -> adaptar para forma real
    return services

def upsert_service(conn, provider, svc):
    cur = conn.cursor()
    # upsert pattern for sqlite
    now = datetime.utcnow().isoformat()
    cur.execute("""
    INSERT INTO services(provider, service_id, group_name, name, credit, meta, available, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(provider, service_id) DO UPDATE SET
      group_name=excluded.group_name,
      name=excluded.name,
      credit=excluded.credit,
      meta=excluded.meta,
      available=1,
      updated_at=excluded.updated_at;
    """, (
        provider,
        svc["service_id"],
        svc.get("group_name") or "",
        svc["name"],
        svc.get("credit") or 0.0,
        json.dumps(svc.get("meta") or {}),
        1,
        now,
        now
    ))
    conn.commit()

def main():
    print("🔎 Fetching services from DHRU provider...")
    data = fetch_services()
    services = normalize_and_extract(data)
    if not services:
        print("⚠️ Parsing returned 0 services — adapta `normalize_and_extract` ao formato real do JSON.")
        return
    conn = sqlite3.connect(DB_PATH)
    provider = "dhrU_iremove"
    for s in services:
        upsert_service(conn, provider, s)
        print(f"Upserted service {s['service_id']} - {s['name']}")
    conn.close()
    print("✅ Sync complete.")

if __name__ == "__main__":
    main()
