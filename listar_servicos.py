import requests
import json

USERNAME = "T-Lux"  # teu username do painel
API_KEY = "I8QMHj1cZIqWWrdZ8tZDX2f2vnGDxttSpC0vHKbdxnbGs9nSlUOLESysHLyE"
API_URL = "https://bulk.iremove.tools/api/dhru/api/index.php"

payload = {
    "username": USERNAME,
    "apiaccesskey": API_KEY,
    "action": "imeiservicelist"
}

print("📤 Pedindo lista de serviços...")
resp = requests.post(API_URL, data=payload, timeout=30)
resp.raise_for_status()

try:
    data = resp.json()
    print("✅ Resposta JSON recebida!\n")

    success_block = data.get("SUCCESS", [])[0]
    service_groups = success_block.get("LIST", {})

    total = 0
    for group_name, group_data in service_groups.items():
        print(f"\n📂 Grupo: {group_name}")
        services = group_data.get("SERVICES", {})
        for sid, sdata in services.items():
            total += 1
            print(f"  ID: {sdata['SERVICEID']} - Nome: {sdata['SERVICENAME']} - Crédito: {sdata['CREDIT']} {success_block.get('CURRENCY', 'USD')}")

    print(f"\n📌 Total de serviços encontrados: {total}")

except ValueError:
    print("⚠️ Resposta não é JSON:\n", resp.text[:500])
