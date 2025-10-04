import requests

USERNAME = "T-Lux"  # teu username do painel
API_KEY = "I8QMHj1cZIqWWrdZ8tZDX2f2vnGDxttSpC0vHKbdxnbGs9nSlUOLESysHLyE"
API_URL = "https://bulk.iremove.tools/api/dhru/api/index.php"

SERVICE_ID = 6   # exemplo: iCloud Bypass iPhone X
IMEI_TESTE = "123456789012345"  # IMEI falso para teste

# Passo 1 → criar ordem
payload_order = {
    "username": USERNAME,
    "apiaccesskey": API_KEY,
    "action": "placeimeiorder",
    "service": SERVICE_ID,
    "imei": IMEI_TESTE
}

print("📤 Enviando ordem de teste...")
resp = requests.post(API_URL, data=payload_order, timeout=30)
resp.raise_for_status()
order_data = resp.json()
print("📦 Resposta da API (ordem):", order_data)

ORDER_ID = order_data.get("SUCCESS", [{}])[0].get("ORDERID")
if not ORDER_ID:
    print("❌ Não foi possível obter ORDERID, abortando.")
    exit()

# Passo 2 → consultar status
payload_status = {
    "username": USERNAME,
    "apiaccesskey": API_KEY,
    "action": "getimeiorder",
    "orderid": ORDER_ID
}

print("\n🔎 Consultando status da ordem...")
resp2 = requests.post(API_URL, data=payload_status, timeout=30)
resp2.raise_for_status()
status_data = resp2.json()
print("📊 Resposta da API (status):", status_data)
