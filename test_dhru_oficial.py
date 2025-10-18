from dhruapi import Dhru

# --- Configuração ---
API_URL = "https://bulk.iremove.tools/api/dhru"
USERNAME = "T-Lux Unlock"
API_KEY = "YF3KXRxJ6oCkTSmR9vlDLjvLTHKRQdLPdG4QllWCJlwrrj6y8lRIBrLzLzVI"

# --- Inicializa o cliente ---
api = Dhru(API_URL, USERNAME, API_KEY)

print("🔗 Testando autenticação e conexão com iRemoval Tools...")

# --- 1) Teste básico: listar serviços ---
try:
    services = api.request("services")
    print("✅ Autenticação OK — Serviços disponíveis:")
    print(services)
except Exception as e:
    print("❌ Erro ao conectar:", e)

# --- 2) Teste IMEI (opcional) ---
try:
    imei_test = {"imei": "356087097368879"}
    res = api.request("getimei", imei_test)
    print("📱 Resposta getimei:", res)
except Exception as e:
    print("❌ Erro ao consultar IMEI:", e)
