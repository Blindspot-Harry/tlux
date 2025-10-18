# dhruapi.py — Cliente Dhru API adaptado para Python (compatível com Dhru Fusion)
import requests
import xml.etree.ElementTree as ET


class Dhru:
    def __init__(self, url, username, api_key):
        self.url = url.rstrip('/')
        self.username = username
        self.api_key = api_key
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }

    # ========================
    #  Função interna de envio
    # ========================
    def _make_request(self, action, params=None):
        root = ET.Element("request")
        ET.SubElement(root, "action").text = action
        ET.SubElement(root, "username").text = self.username
        ET.SubElement(root, "api_key").text = self.api_key

        if params:
            for k, v in params.items():
                ET.SubElement(root, k).text = str(v)

        xml_data = "<?xml version='1.0'?>\n" + ET.tostring(root, encoding="unicode")
        data = {"xml": xml_data}

        try:
            # ✅ Usa o endpoint completo do Dhru original
            url = self.url.rstrip("/") + "/api/index.php"

            # ✅ Emula o Dhru PHP client (para evitar bloqueio por firewall)
            headers = {
                "User-Agent": "Dhru Fusion PHP Client",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            resp = requests.post(url, data=data, headers=headers, timeout=25, verify=False)
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                return {"raw": resp.text}
        except Exception as e:
            return {"error": str(e)}

    # ========================
    #  Métodos públicos
    # ========================
    def account_info(self):
        """Retorna informações da conta (saldo, nome, status)"""
        return self._make_request("accountinfo")

    def services(self):
        """Retorna lista de serviços disponíveis"""
        return self._make_request("services")

    def get_imei(self, imei):
        """Consulta informações de um IMEI específico"""
        return self._make_request("getimei", {"imei": imei})

    def place_imei_order(self, imei, service_id):
        """Cria uma ordem de desbloqueio IMEI"""
        return self._make_request("placeimeiorder", {"imei": imei, "serviceid": service_id})


# ========================
#  Teste rápido opcional
# ========================
if __name__ == "__main__":
    api = Dhru(
        "https://bulk.iremove.tools/api/dhru",
        "T-Lux Unlock",
        "YF3KXRxJ6oCkTSmR9vlDLjvLTHKRQdLPdG4QllWCJlwrrj6y8lRIBrLzLzVI"
    )

    print("🔗 Testando conexão com iRemoval Tools...")
    print("📘 Conta:", api.account_info())
    print("📦 Serviços:", api.services())
    print("📱 IMEI:", api.get_imei("356087097368879"))
