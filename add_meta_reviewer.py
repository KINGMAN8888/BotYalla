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
        # 1. Ensure the user exists and is an admin
        c.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        
        if row:
            user_id = row[0]
            print(f"User {username} exists (ID: {user_id}). Updating role to admin...")
            c.execute("UPDATE users SET role = 'admin', pw_hash = ? WHERE id = ?", (pw_hash, user_id))
        else:
            print(f"Creating new user {username} with admin role...")
            c.execute(
                "INSERT INTO users (username, pw_hash, role, is_blocked, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, pw_hash, 'admin', 0, now)
            )
            user_id = c.lastrowid
            
        # 2. Verify the email by adding to settings
        print("Verifying email...")
        c.execute(
            "INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user_id, 'email_verified_at', str(now))
        )
        
        # 3. Remove any verify_required flag if it exists just to be safe
        c.execute("DELETE FROM settings WHERE user_id = ? AND key = 'verify_required'", (user_id,))
        
        conn.commit()
        print(f"SUCCESS! {username} is now an ADMIN and their email is VERIFIED.")
        print(f"Password: {password}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    add_meta_reviewer()
