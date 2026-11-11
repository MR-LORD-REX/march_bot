import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server.app import create_app


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
            "server.admin.panel.routes.consume_login_token",
            AsyncMock(return_value=None),
        ):
            response = self.client.get("/admin/login?token=bad", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("login_expired", response.headers["location"])

    def test_panel_blocks_owner_authority_escalation(self):
        with patch(
            "server.admin.panel.routes.require_panel_user",
            AsyncMock(return_value={"telegram_id": 1, "authority": "owner"}),
        ):
            response = self.client.post(
                "/admin/api/admins/99/authority",
                json={"authority": "owner"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("reserved", response.json()["detail"])

    def test_moderator_cannot_mutate_users(self):
        with patch(
            "server.admin.panel.routes.require_panel_user",
            AsyncMock(return_value={"telegram_id": 2, "authority": "moderator"}),
        ):
            response = self.client.post(
                "/admin/api/users/99/action",
                json={"action": "warn"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("authority", response.json()["detail"])

    def test_broadcast_rejects_invalid_html_before_queueing(self):
        with patch(
            "server.admin.panel.routes.require_panel_user",
            AsyncMock(return_value={"telegram_id": 2, "authority": "admin"}),
        ), patch("server.admin.panel.routes.enqueue", AsyncMock()) as enqueue:
            response = self.client.post(
                "/admin/api/broadcasts",
                json={
                    "audience": "users",
                    "body": "<message>bad</message>",
                    "parse_mode": "HTML",
                },
            )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Telegram HTML", response.json()["detail"])
        enqueue.assert_not_awaited()

    def test_user_capabilities_split_read_and_mutation(self):
        moderator = {
            "authority": "moderator",
            "telegram_id": 2,
            "capabilities": {
                "ban": False,
                "warn": True,
                "reset_warns": False,
                "set_language": False,
            },
        }
        self.assertFalse(moderator["capabilities"]["ban"])
        self.assertTrue(moderator["capabilities"]["warn"])


if __name__ == "__main__":
    unittest.main()