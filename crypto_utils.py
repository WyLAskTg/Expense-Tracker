import hashlib
import hmac
import os
from pathlib import Path


MAGIC = b"PETENC1\n"
ITERATIONS = 240_000
SALT_SIZE = 16
NONCE_SIZE = 16
TAG_SIZE = 32


def _derive_keys(password, salt):
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS, dklen=64)
    return key[:32], key[32:]


def _keystream(key, nonce, length):
    blocks = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
        counter += 1
    return b"".join(blocks)[:length]


def _xor_bytes(left, right):
    return bytes(a ^ b for a, b in zip(left, right))


def encrypt_bytes(data, password):
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    enc_key, mac_key = _derive_keys(password, salt)
    encrypted = _xor_bytes(data, _keystream(enc_key, nonce, len(data)))
    header = MAGIC + ITERATIONS.to_bytes(4, "big") + salt + nonce
    tag = hmac.new(mac_key, header + encrypted, hashlib.sha256).digest()
    return header + encrypted + tag


def decrypt_bytes(payload, password):
    if not payload.startswith(MAGIC):
        raise ValueError("Encrypted file has an unsupported format.")

    offset = len(MAGIC)
    iterations = int.from_bytes(payload[offset : offset + 4], "big")
    offset += 4
    salt = payload[offset : offset + SALT_SIZE]
    offset += SALT_SIZE
    nonce = payload[offset : offset + NONCE_SIZE]
    offset += NONCE_SIZE
    encrypted = payload[offset:-TAG_SIZE]
    tag = payload[-TAG_SIZE:]

    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=64)
    enc_key, mac_key = key[:32], key[32:]
    expected = hmac.new(mac_key, payload[:-TAG_SIZE], hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("Password is incorrect or encrypted data is damaged.")
    return _xor_bytes(encrypted, _keystream(enc_key, nonce, len(encrypted)))


def encrypt_file(source_path, destination_path, password):
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    temp_path.write_bytes(encrypt_bytes(source.read_bytes(), password))
    temp_path.replace(destination)
    return destination


def decrypt_file(source_path, destination_path, password):
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    temp_path.write_bytes(decrypt_bytes(source.read_bytes(), password))
    temp_path.replace(destination)
    return destination
