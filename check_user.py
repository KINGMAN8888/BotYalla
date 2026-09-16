import sqlite3
conn = sqlite3.connect('botyalla.db')
c = conn.cursor()
c.execute("SELECT id, username, role FROM users WHERE username='meta_reviewer@botyalla.com'")
print(c.fetchone())
