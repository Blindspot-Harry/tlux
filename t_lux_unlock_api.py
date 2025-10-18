# ============================================
# T-Lux Unlock — Integração oficial com iRemoval (Dhru API)
# ============================================

import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# ===============================
#  Configurações de ambiente
# ===============================
DHRU_USERNAME = os.getenv("DHRU_USERNAME", "T-Lux Unlock")
DHRU_API_KEY = os.getenv("DHRU_API_KEY", "YF3KXRxJ6oCkTSmR9vlDLjvLTHKRQdLPdG4QllWCJlwrrj6y8lRIBrLzLzVI" )
DHRU_API_URL = os.getenv("DHRU_API_URL", "https://bulk.iremove.tools/api/dhru/api/index.php")

# ===============================
#  Cliente Dhru API
# ===============================
class DhruClient:
    def __init__(self, url, username, api_key):
        self.url = url
        self.username = username
        self.api_key = api_key

    def _request(self, action, params=None):
        """
        Monta e envia o XML padrão Dhru API
        """
        root = ET.Element("request")
        ET.SubElement(root, "action").text = action
        ET.SubElement(root, "username").text = self.username
        ET.SubElement(root, "api_key").text = self.api_key

        if params:
            for k, v in params.items():
                ET.SubElement(root, k).text = str(v)

        xml_data = "<?xml version='1.0'?>\n" + ET.tostring(root, encoding="unicode")

        headers = {
            "User-Agent": "Dhru Fusion PHP Client",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            resp = requests.post(
                self.url,
                data={"xml": xml_data},
                headers=headers,
                timeout=30,
                verify=False
            )
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                return {"raw": resp.text}
        except Exception as e:
            return {"error": str(e)}

    # ========= Métodos públicos ==========
    def account_info(self):
        return self._request("accountinfo")

    def get_services(self):
        return self._request("services")

    def get_imei_info(self, imei):
        return self._request("getimei", {"imei": imei})

    def place_imei_order(self, imei, service_id):
        """
        Cria ordem de desbloqueio
        """
        return self._request("placeimeiorder", {"imei": imei, "serviceid": service_id})


# ===============================
#  Função de integração principal
# ===============================
def enviar_desbloqueio(imei: str, service_id: int, user_email: str):
    """
    Envia ordem de desbloqueio para iRemoval e grava logs no banco (posteriormente).
    """
    api = DhruClient(DHRU_API_URL, DHRU_USERNAME, DHRU_API_KEY)
    response = api.place_imei_order(imei, service_id)

    # Monta log simples para debug inicial
    log = {
        "timestamp": datetime.utcnow().isoformat(),
        "imei": imei,
        "service_id": service_id,
        "user_email": user_email,
        "response": response,
    }

    # Mostra no terminal
    print("📤 [T-Lux → iRemoval] Enviado:")
    print(log)

    # Em produção: salvar em tabela logs_desbloqueio
    return response


# ===============================
#  Teste rápido local
# ===============================
if __name__ == "__main__":
    print("🔗 Testando comunicação com iRemoval...")
    api = DhruClient(DHRU_API_URL, DHRU_USERNAME, DHRU_API_KEY)

    print("📘 Conta:", api.account_info())
    print("📦 Serviços:", api.get_services())
    print("📱 IMEI Teste:", api.get_imei_info("356087097368879"))
