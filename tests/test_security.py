import unittest

from security import hash_password, verify_password


class SecurityTest(unittest.TestCase):
    def test_password_hash_verification(self):
        salt, digest = hash_password("correct horse")

        self.assertTrue(verify_password("correct horse", salt, digest))
        self.assertFalse(verify_password("wrong horse", salt, digest))


if __name__ == "__main__":
    unittest.main()
