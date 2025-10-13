import sqlite3

ADMIN_EMAIL = "arrymauai3@gmail.com"

conn = sqlite3.connect("t-lux.db")
c = conn.cursor()

# Remove todos os usuários exceto o admin
c.execute("DELETE FROM users WHERE email != ?", (ADMIN_EMAIL,))

# Resetar autoincrement
c.execute("DELETE FROM sqlite_sequence WHERE name='users';")

conn.commit()
conn.close()
print(f"✅ Apenas o admin {ADMIN_EMAIL} foi mantido no banco!")
