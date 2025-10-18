# dhru_client.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

DHRU_ENDPOINT = os.getenv("DHRU_API_URL", "https://bulk.iremove.tools/api/dhru/api/index.php")
DHRU_USERNAME = os.getenv("DHRU_USERNAME", "tluxunlock@t-lux.store")
DHRU_API_KEY = os.getenv("DHRU_API_KEY", "")

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
}

def build_xml(action: str, imei: str = None, extra_fields: dict = None) -> str:
    extra_xml = ""
    if extra_fields:
        for k, v in extra_fields.items():
            extra_xml += f"<{k}>{v}</{k}>"
    imei_tag = f"<imei>{imei}</imei>" if imei else ""
    xml = (
        '<?xml version="1.0"?>'
        f"<request><action>{action}</action>"
        f"<username>{DHRU_USERNAME}</username>"
        f"<api_key>{DHRU_API_KEY}</api_key>"
        f"{imei_tag}{extra_xml}</request>"
    )
    return xml

def dhru_post(xml: str, timeout: int = 15) -> dict:
    try:
        payload = {"xml": xml}
        resp = requests.post(DHRU_ENDPOINT, headers=HEADERS, data=payload, timeout=timeout)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return {"raw_text": resp.text}
    except requests.RequestException as e:
        return {"error": str(e)}

def test_getimei(imei: str):
    xml = build_xml(action="getimei", imei=imei)
    return dhru_post(xml)

def list_services():
    xml = build_xml(action="services")
    return dhru_post(xml)

def submit_order(imei: str, service: str, country: str = None, **kwargs):
    extra = {"service": service}
    if country:
        extra["country"] = country
    extra.update(kwargs)
    xml = build_xml(action="submit", imei=imei, extra_fields=extra)
    return dhru_post(xml)

if __name__ == "__main__":
    print("DHRU_ENDPOINT:", DHRU_ENDPOINT)
    print("DHRU_USERNAME:", DHRU_USERNAME)
    print("DHRU_API_KEY (len):", len(DHRU_API_KEY))
    # quick smoke test removed for safety; use the test script below for real calls.
