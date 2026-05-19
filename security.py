import base64
import hashlib
import hmac
import os


ITERATIONS = 120_000


def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return (
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password, salt_text, digest_text):
    salt = base64.b64decode(salt_text.encode("ascii"))
    _, candidate = hash_password(password, salt=salt)
    return hmac.compare_digest(candidate, digest_text)
