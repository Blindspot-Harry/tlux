import requests

xml_data = """<?xml version="1.0"?>
<request>
  <action>getimei</action>
  <username>i39337</username>
  <api_key>YF3KXRxJ6oCkTSmR9vlDLjvLTHKRQdLPdG4QllWCJlwrrj6y8lRIBrLzLzVI</api_key>
  <imei>356087097368879</imei>
</request>"""

data = {"xml": xml_data}
headers = {
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Dhru Fusion PHP Client"
}

print("🔗 Sending POST to iRemoval Tools...")
resp = requests.post(
    "https://bulk.iremove.tools/api/dhru/api/index.php",
    data=data,
    headers=headers,
    timeout=25,
)
print(resp.status_code)
print(resp.text)
