import requests

xml = """<?xml version="1.0"?>
<request>
  <action>getimei</action>
  <username>T-Lux Unlock</username>
  <api_key>YF3KXRxJ6oCkTSmR9vlDLjvLTHKRQdLPdG4QllWCJlwrrj6y8lRIBrLzLzVI</api_key>
  <imei>356087097368879</imei>
</request>"""

r = requests.post("https://bulk.iremove.tools/api/dhru/api/index.php",
                  headers={"Accept":"application/json"},
                  data={"xml": xml},
                  timeout=15)

print(r.status_code)
print(r.text)
