#!/usr/bin/env python3
"""
Teste seguro e integração mínima com bulk.iremove.tools (DHru).
 - Usa a API key que você forneceu.
 - Tenta enviar pedidos com alguns parâmetros comuns.
 - Trata respostas JSON ou HTML sem quebrar.
 - Atualiza SQLite: insere em `orders` e define `users.ativo = 1` quando sucesso.
 
Como usar:
    python3 test_iremoval_full.py

Edite as variáveis abaixo: IMEI_TO_TEST e USER_EMAIL para o teste real.
"""
import requests
import sqlite3
import time
import sys
from typing import Optional

# ---------- CONFIGURAÇÃO (edita conforme necessário) ----------
URL = "https://bulk.iremove.tools/api/dhru/api/index.php"
API_KEY = "I8QMHj1cZIqWWrdZ8tZDX2f2vnGDxttSpC0vHKbdxnbGs9nSlUOLESysHLyE"

# IMEI e email de teste — substitui pelos valores que quiseres testar
IMEI_TO_TEST = "123456789012345"   # <-- substitui aqui
USER_EMAIL = "teste@cliente.com"   # <-- substitui aqui

# Caminho do DB (ajusta se for outro)
DB_PATH = "t-lux.db"

# Lista de conjuntos de parâmetros a tentar (varia por fornecedor)
PARAM_SETS = [
    {"imei": IMEI_TO_TEST, "api_key": API_KEY},
    # alguns provedores pedem service_id, country, imei_type, etc. adiciona tentativas
    {"imei": IMEI_TO_TEST, "api_key": API_KEY, "service": "dhru"},
    {"imei": IMEI_TO_TEST, "api_key": API_KEY, "service_id": "1"},
    {"imei": IMEI_TO_TEST, "api_key": API_KEY, "service_id": "1", "imei_type": "1"},
    # se tiveres um 'order_type' ou 'country' conhecido, acrescenta aqui
]

# Timeout para requests
REQUEST_TIMEOUT = 30

# ---------- FUNÇÕES AUXILIARES ----------
def pretty_print_response(resp: requests.Response):
    print("Status:", resp.status_code)
    ct = resp.headers.get("Content-Type", "")
    # tenta decodificar JSON; se falhar, imprime texto
    try:
        j = resp.json()
        print("JSON Response:", j)
        return j
    except Exception:
        print("Text Response (first 800 chars):")
        print(resp.text[:800])
        return None

def update_sqlite_on_success(email: str, imei: str, api_response: dict, db_path: str = DB_PATH):
    """
    Insere na tabela orders e define users.ativo = 1 se o usuário existir.
    Se as tabelas não existirem, cria um esquema mínimo.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Cria tabelas mínimas se não existirem
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        ativo INTEGER DEFAULT 0
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        imei TEXT,
        response TEXT,
        created_at TEXT
    );
    """)

    # Insert order
    cursor.execute(
        "INSERT INTO orders (email, imei, response, created_at) VALUES (?, ?, ?, ?)",
        (email, imei, str(api_response), time.strftime("%Y-%m-%d %H:%M:%S"))
    )

    # Tenta atualizar user como ativo
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE users SET ativo = 1 WHERE email = ?", (email,))
        print(f"[DB] Usuário '{email}' marcado como ativo.")
    else:
        # Se usuário não existe, podes criar um registro minimal
        cursor.execute("INSERT INTO users (email, ativo) VALUES (?, ?)", (email, 1))
        print(f"[DB] Usuário '{email}' criado e marcado como ativo.")

    conn.commit()
    conn.close()

# ---------- FLUXO PRINCIPAL ----------
def main():
    print("=== Teste iRemoval/T-Lux — Iniciando ===")
    print("Endpoint:", URL)
    print("IMEI:", IMEI_TO_TEST)
    print("Email:", USER_EMAIL)
    print()

    last_json = None
    for idx, params in enumerate(PARAM_SETS, start=1):
        print(f"--- Tentativa {idx}/{len(PARAM_SETS)} com parâmetros: {params}")
        try:
            resp = requests.post(URL, json=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            print("Erro de requisição:", e)
            continue

        parsed = pretty_print_response(resp)

        # interpretações rápidas comuns
        if isinstance(parsed, dict):
            last_json = parsed
            # ver mensagens de erro/sucesso padronizadas
            if "ERROR" in parsed:
                try:
                    # tenta extrair mensagem
                    msg = parsed["ERROR"][0].get("MESSAGE", parsed["ERROR"])
                    print("[API] ERROR:", msg)
                    # se for authentication failed, parar e pedir verificação de chave
                    if "Authentication" in str(msg) or "auth" in str(msg).lower():
                        print("[AÇÃO] Authentication Failed — verifica a API key no painel do fornecedor.")
                        # NÃO return — experimenta outras combinações caso haja campos faltando
                except Exception:
                    print("[API] ERROR (formato inesperado):", parsed["ERROR"])
            elif "SUCCESS" in parsed or "success" in {k.lower(): v for k,v in parsed.items()}:
                print("[API] Sucesso detectado. Tentando atualizar DB e liberar acesso...")
                update_sqlite_on_success(USER_EMAIL, IMEI_TO_TEST, parsed, DB_PATH)
                print("=== Fluxo concluído com sucesso ===")
                return
            else:
                # outras chaves inesperadas
                print("[API] Resposta sem chave ERROR/SUCCESS — ver conteúdo.")
        else:
            # resposta não-JSON (HTML ou texto) — mostra e continua
            print("[INFO] Resposta não JSON; checa manualmente.")

        print()  # salto de linha entre tentativas

    # depois de todas as tentativas
    print("=== Todas as tentativas concluídas ===")
    if last_json:
        if "ERROR" in last_json and any("Authentication" in e.get("MESSAGE","") for e in last_json.get("ERROR",[])):
            print("[RESUMO] Falha por autenticação. Ações recomendadas:")
            print(" - Confirma que a API key está ativa no painel: https://bulk.iremove.tools/user-settings")
            print(" - Verifica se precisas de campos adicionais (service_id, service, country, imei_type).")
            print(" - Se a chave for nova, pode precisar de ativação pelo suporte.")
        else:
            print("[RESUMO] Resposta recebida mas sem sucesso claro. Revisa o conteúdo acima.")
    else:
        print("[RESUMO] Nenhuma resposta JSON recebida. Verifica rede, endpoint e documentação.")

if __name__ == "__main__":
    main()
