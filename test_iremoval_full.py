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
# test_iremoval_full.py
from dhru_client import list_services, test_getimei
import json

def pretty_print(resp):
    print(json.dumps(resp, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    print("1) List services (this confirms auth + returns available services)...")
    svc = list_services()
    pretty_print(svc)

    print("\n2) Test getimei (uses sample/test IMEI; expect 'Invalid IMEI' or similar if IMEI not in DB)")
    test_imei = "356087097368879"
    res = test_getimei(test_imei)
    pretty_print(res)
