from dhruapi import Dhru

api = Dhru(
    "https://bulk.iremove.tools/api/dhru",  # mantém esta base
    "T-Lux Unlock",
    "YF3KXRxJ6oCkTSmR9vlDLjvLTHKRQdLPdG4QllWCJlwrrj6y8lRIBrLzLzVI"
)

print("🔗 Testing connection with iRemoval Tools...")

print("📘 Account Info:")
print(api.account_info())

print("\n📦 Services:")
print(api.services())

print("\n📱 IMEI Test:")
print(api.get_imei("356087097368879"))
