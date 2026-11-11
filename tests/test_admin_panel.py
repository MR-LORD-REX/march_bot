import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from bot.api.webhook import create_app


class AdminPanelTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(SimpleNamespace(), dp=None, mode="test")
        self.client = TestClient(self.app)

    def test_panel_index_redirects_anonymous_users(self):
        response = self.client.get("/admin/", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["location"].startswith("/admin/login-required"))

    def test_panel_api_rejects_anonymous_users(self):
        response = self.client.get("/admin/api/summary")
        self.assertEqual(response.status_code, 401)

    def test_panel_login_shell_is_public(self):
        response = self.client.get("/admin/login-required")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Admin access", response.text)

    def test_panel_static_allowlist_blocks_unknown_files(self):
        response = self.client.get("/admin/static/secrets.txt")
        self.assertEqual(response.status_code, 404)

    def test_anonymous_cannot_read_reports(self):
        response = self.client.get("/admin/api/reports")
        self.assertEqual(response.status_code, 401)

    def test_anonymous_cannot_post_replies(self):
        response = self.client.post(
            "/admin/api/reports/1/reply",
            json={"body": "hello"},
        )
        self.assertEqual(response.status_code, 401)

    def test_login_rejects_reused_token(self):
        with patch(
            "bot.admin.panel.routes.consume_login_token",
            AsyncMock(return_value=None),
        ):
            response = self.client.get("/admin/login?token=bad", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("login_expired", response.headers["location"])

    def test_panel_blocks_owner_authority_escalation(self):
        with patch(
            "bot.admin.panel.routes.require_panel_user",
            AsyncMock(return_value={"telegram_id": 1, "authority": "owner"}),
        ):
            response = self.client.post(
                "/admin/api/admins/99/authority",
                json={"authority": "owner"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("reserved", response.json()["detail"])

if __name__ == "__main__":
    unittest.main()