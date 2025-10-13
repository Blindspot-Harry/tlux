import requests
import json
import os

USERNAME = os.getenv("DHRU_USERNAME", "T-Lux")
API_KEY = os.getenv("DHRU_API_KEY", "I8QMHj1cZIqWWrdZ8tZDX2f2vnGDxttSpC0vHKbdxnbGs9nSlUOLESysHLyE")
API_URL = os.getenv("DHRU_API_URL", "https://bulk.iremove.tools/api/dhru/api/index.php")

payload = {
    "username": USERNAME,
    "apiaccesskey": API_KEY,
    "action": "imeiservicelist"
}


def get_structured_services():
    """Retorna lista estruturada dos grupos e serviços da DHRU API."""
    print("📤 Pedindo lista de serviços...")
    resp = requests.post(API_URL, data=payload, timeout=30)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        print("⚠ Resposta não é JSON:\n", resp.text[:500])
        return []

    success_block = data.get("SUCCESS", [])[0]
    service_groups = success_block.get("LIST", {})

    result = []
    for group_name, group_data in service_groups.items():
        services = group_data.get("SERVICES", {})
        items = []
        for sid, sdata in services.items():
            try:
                credit_value = float(str(sdata.get("CREDIT", "0")).split()[0])
            except:
                credit_value = 0.0

            items.append({
                "id": str(sdata["SERVICEID"]),
                "name": sdata["SERVICENAME"],
                "credit": credit_value,
                "currency": "USD"
            })
        result.append({"group": group_name, "items": items})
    return result


if __name__ == "__main__":
    # versão de exibição (igual à tua)
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
                print(f"  ID: {sdata['SERVICEID']} - Nome: {sdata['SERVICENAME']} - Crédito: {sdata['CREDIT']}")
        print(f"\n📌 Total de serviços encontrados: {total}")

    except ValueError:
        print("⚠ Resposta não é JSON:\n", resp.text[:500])
