import os, requests, xml.etree.ElementTree as ET

USERNAME = "i39337"  # ← usa este
API_KEY = "zyEwIt7MhlDdpvndFAGcgpu4o5Bu17IvNYkTe774oYgK6o97LaNHmV0bu6KN"
ENDPOINT = "https://bulk.iremove.tools/api/dhru"

xml = f"""<xml>
  <method>imeiservices</method>
  <key>{API_KEY}</key>
  <username>{USERNAME}</username>
  <imei>123456789012345</imei>
</xml>"""

r = requests.post(ENDPOINT, data=xml.encode("utf-8"), headers={"Content-Type":"application/xml"}, timeout=15)
print("status:", r.status_code)
print("resp head:", r.headers.get("content-type"))
print("resp preview:", r.text[:800])
# tenta parsear se for XML
try:
    root = ET.fromstring(r.text)
    print("parsed root tag:", root.tag)
except ET.ParseError:
    print("response is not valid XML")
