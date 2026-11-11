import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from bot.api.webhook import create_app


class MiniAppApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(SimpleNamespace(), dp=None, mode="test")
        self.client = TestClient(self.app)

    def test_health_endpoint(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_submit_team_rejects_invalid_init_data(self):
        response = self.client.post(
            "/submit_team",
            json={
                "slot": 1,
                "init_data": "auth_date=1&user=%7B%22id%22%3A1%7D&hash=bad",
                "teammates": [
                    {"characterId": "1", "lightCone": "1"},
                    {"characterId": "2", "lightCone": "2"},
                    {"characterId": "3", "lightCone": "3"},
                ],
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("initData", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()