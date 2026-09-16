import sqlite3
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from auth import hash_password

DB_PATH = 'botyalla.db'

def reset_meta_reviewer():
    target_usernames = ['meta_reviewer', 'meta_reviewer@botyalla.com']
    final_username = 'meta_reviewer@botyalla.com'
    password = 'MetaReview2024!'
    
    pw_hash = hash_password(password)
    now = int(time.time())
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # 1. Delete existing users that match either username to avoid conflicts
        for uname in target_usernames:
            c.execute("SELECT id FROM users WHERE username = ?", (uname,))
            row = c.fetchone()
            if row:
                user_id = row[0]
                print(f"Deleting conflicting user '{uname}' (ID: {user_id})...")
                c.execute("DELETE FROM users WHERE id = ?", (user_id,))
                c.execute("DELETE FROM settings WHERE user_id = ?", (user_id,))
        
        # 2. Create the fresh admin user
        print(f"Creating fresh user '{final_username}' with admin role...")
        c.execute(
            "INSERT INTO users (username, pw_hash, role, is_blocked, created_at) VALUES (?, ?, ?, ?, ?)",
            (final_username, pw_hash, 'admin', 0, now)
        )
        new_user_id = c.lastrowid
        
        # 3. Add email verification and actual email to settings
        settings_to_insert = [
            (new_user_id, 'email', final_username),
            (new_user_id, 'email_verified_at', str(now))
        ]
        
        for user_id, key, value in settings_to_insert:
            c.execute(
                "INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
                (user_id, key, value)
            )
            
        conn.commit()
        print(f"✅ SUCCESS! '{final_username}' is now recreated as a clean ADMIN with verified email.")
        print(f"🔑 Password: {password}")
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    reset_meta_reviewer()
