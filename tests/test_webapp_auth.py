import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import quote, unquote

from shared.auth.telegram_webapp import InitDataError, verify_init_data


def sign(fields: dict[str, str], token: str = "123:test") -> str:
    """Create initData exactly as Telegram does: hash decoded values."""
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return "&".join(
        f"{key}={quote(value, safe='')}" for key, value in {**fields, "hash": signature}.items()
    )


class TelegramWebAppTests(unittest.TestCase):
    def test_verify_init_data_returns_signed_user(self):
        fields = {
            "auth_date": str(int(time.time())),
            "query_id": "abc",
            "user": json.dumps({"id": 42, "username": "trailblazer"}),
        }
        result = verify_init_data(sign(fields), "123:test")
        self.assertEqual(result.telegram_id, 42)
        self.assertEqual(result.username, "trailblazer")

    def test_rejects_stale_init_data(self):
        fields = {
            "auth_date": str(int(time.time()) - 600),
            "user": json.dumps({"id": 42}),
        }
        with self.assertRaises(InitDataError):
            verify_init_data(sign(fields), "123:test")

    def test_rejects_tampered_user(self):
        fields = {
            "auth_date": str(int(time.time())),
            "user": json.dumps({"id": 42}),
        }
        signed = sign(fields)
        tampered = signed.replace(quote(fields["user"]), quote(json.dumps({"id": 99})))
        self.assertNotEqual(signed, tampered)
        with self.assertRaises(InitDataError):
            verify_init_data(tampered, "123:test")


if __name__ == "__main__":
    unittest.main()