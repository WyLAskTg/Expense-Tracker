import unittest

from crypto_utils import decrypt_bytes, encrypt_bytes
from security import hash_password, verify_password
from update_checker import is_newer_version, version_tuple


class SecurityTest(unittest.TestCase):
    def test_password_hash_verification(self):
        salt, digest = hash_password("correct horse")

        self.assertTrue(verify_password("correct horse", salt, digest))
        self.assertFalse(verify_password("wrong horse", salt, digest))

    def test_encrypted_payload_round_trip(self):
        payload = encrypt_bytes(b"private data", "secret")

        self.assertEqual(decrypt_bytes(payload, "secret"), b"private data")
        with self.assertRaises(ValueError):
            decrypt_bytes(payload, "bad secret")

    def test_version_comparison(self):
        self.assertEqual(version_tuple("v25.5.3"), (25, 5, 3))
        self.assertTrue(is_newer_version("v25.5.4", "v25.5.3"))
        self.assertFalse(is_newer_version("v25.5.3", "v25.5.3"))


if __name__ == "__main__":
    unittest.main()
