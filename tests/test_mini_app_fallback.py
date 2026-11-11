import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import Chat, Message, PhotoSize
from server.routes import mini_app
from shared.auth.handoff import Handoff


class MiniAppFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_uses_new_message_for_handoff(self):
        photo = PhotoSize(file_id="photo", file_unique_id="unique", width=1, height=1)
        sent = Message(
            message_id=12,
            date=datetime.now(timezone.utc),
            chat=Chat(id=-100, type="supergroup"),
            photo=[photo],
        )

        bot = SimpleNamespace(
            me=AsyncMock(return_value=SimpleNamespace(username="march_bot")),
            edit_message_media=AsyncMock(side_effect=RuntimeError("cannot edit")),
            send_photo=AsyncMock(return_value=sent),
        )
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(bot=bot)))
        user = SimpleNamespace(telegram_id=42, username="trailblazer")
        handoff = Handoff(
            token="token",
            telegram_id=42,
            chat_id=-100,
            message_id=11,
            uid=100,
            slot=1,
        )
        result = SimpleNamespace(card=object())

        async def fake_claim(_token, _telegram_id):
            return handoff

        def fake_keyboard(*_args, **_kwargs):
            return "kb"

        class Session:
            async def __aenter__(self):
                return SimpleNamespace()

            async def __aexit__(self, *args):
                return None

        body = mini_app.SubmitTeamRequest(
            slot=1,
            handoff="token",
            init_data="signed",
            teammates=[
                {"characterId": "1", "lightCone": "1"},
                {"characterId": "2", "lightCone": "2"},
                {"characterId": "3", "lightCone": "3"},
            ],
        )
        next_handoff = Handoff(
            token="next",
            telegram_id=42,
            chat_id=-100,
            message_id=12,
            uid=100,
            slot=1,
        )

        with patch.object(mini_app, "claim_handoff", fake_claim), patch.object(
            mini_app, "verify_init_data", return_value=user
        ), patch(
            "honkai_cards.Teammate", side_effect=lambda **kwargs: SimpleNamespace(**kwargs)
        ), patch(
            "bot.services.cards.get_custom_card", AsyncMock(return_value=result)
        ), patch.object(mini_app, "_card_file", AsyncMock(return_value="file")), patch.object(
            mini_app, "session_factory", lambda: Session()
        ), patch.object(mini_app, "GameIDs_repo") as repo_cls, patch.object(
            mini_app, "UserRepo"
        ) as user_repo, patch.object(
            mini_app, "create_handoff", AsyncMock(return_value=next_handoff)
        ), patch.object(
            mini_app, "make_back_kb", side_effect=fake_keyboard
        ), patch.object(Message, "edit_reply_markup", AsyncMock()) as edit_markup:
            repo_cls.return_value.get_active_UID = AsyncMock(
                return_value=SimpleNamespace(game_id=100)
            )
            user_repo.return_value.get_by_tele_id = AsyncMock(
                return_value=SimpleNamespace()
            )
            response = await mini_app.submit_team(body, request)

        self.assertEqual(response["note"], "sent as new message")
        bot.send_photo.assert_awaited_once()
        self.assertNotIn("reply_markup", bot.send_photo.await_args.kwargs)
        edit_markup.assert_awaited_once_with(reply_markup="kb")



class HandoffCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_lookup_only_returns_issued_handoff(self):
        handoff = Handoff(
            token="abc123",
            telegram_id=42,
            chat_id=-100,
            message_id=11,
            uid=100,
            slot=1,
        )
        client = SimpleNamespace(get=AsyncMock(return_value="abc123"))

        with patch("shared.auth.handoff._client", return_value=client), patch(
            "shared.auth.handoff.get_handoff", AsyncMock(return_value=handoff)
        ):
            from shared.auth.handoff import legacy_handoff

            resolved = await legacy_handoff(42, 100, 1, -100, 11)

        self.assertEqual(resolved, handoff)

    async def test_legacy_lookup_rejects_forged_destination(self):
        from shared.auth.handoff import HandoffError, legacy_handoff

        client = SimpleNamespace(get=AsyncMock(return_value=None))
        with patch("shared.auth.handoff._client", return_value=client):
            with self.assertRaises(HandoffError):
                await legacy_handoff(42, 100, 1, -999, 777)

    def test_legacy_start_param_has_five_segments(self):
        from bot.handlers.cards.kb import make_back_kb

        kb = make_back_kb(
            42,
            1,
            100,
            "march_bot",
            -100,
            11,
            handoff_reference="compact",
        )
        url = kb.inline_keyboard[-1][0].url
        startapp = url.split("startapp=", 1)[1]
        parts = startapp.split("_")
        self.assertGreaterEqual(len(parts), 4)
        self.assertEqual(parts[:4], ["100", "1", "-100", "11"])
        self.assertEqual("_".join(parts[4:]), "march_bot")

if __name__ == "__main__":
    unittest.main()