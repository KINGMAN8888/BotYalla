"""تشفير كلمات المرور والتحقق منها."""
from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(pw: str) -> str:
    return generate_password_hash(pw)

def verify_password(pw: str, pw_hash: str) -> bool:
    try:
        return check_password_hash(pw_hash, pw)
    except Exception:
        return False
