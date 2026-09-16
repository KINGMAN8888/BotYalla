import sqlite3
import time
import os
import sys

# Append the project path to sys.path so we can import auth
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from auth import hash_password

DB_PATH = 'botyalla.db'

def add_meta_reviewer():
    username = 'meta_reviewer@botyalla.com'
    password = 'MetaReview2024!'
    
    pw_hash = hash_password(password)
    now = int(time.time())
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        c.execute(
            "INSERT INTO users (username, pw_hash, role, is_blocked, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, pw_hash, 'admin', 0, now)
        )
        conn.commit()
        print(f"✅ User '{username}' created successfully with full ADMIN privileges.")
        print(f"🔑 Password: {password}")
    except sqlite3.IntegrityError:
        print(f"⚠️ User '{username}' already exists. Updating role to admin and resetting password...")
        c.execute(
            "UPDATE users SET role = 'admin', pw_hash = ? WHERE username = ?", 
            (pw_hash, username)
        )
        conn.commit()
        print(f"✅ User '{username}' updated to ADMIN successfully.")
        print(f"🔑 New Password: {password}")
    finally:
        conn.close()

if __name__ == '__main__':
    add_meta_reviewer()
