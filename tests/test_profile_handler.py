import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.cards.profile import handle_ccard
from bot.services.cards import CharRes


class HandleCcardTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_ccard_reports_failure_when_card_payload_is_missing(self):
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=123),
            data="C_card:123:1",
            bot=SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(username="march_bot"))),
            answer=AsyncMock(),
            message=SimpleNamespace(
                chat=SimpleNamespace(id=-100),
                message_id=99,
                edit_text=AsyncMock(),
                edit_media=AsyncMock(),
            ),
        )

        with patch(
            "bot.handlers.cards.profile.get_character_card",
            AsyncMock(return_value=CharRes(cached=False, card=None, data="1")),
        ), patch(
            "bot.handlers.cards.profile.GameIDs_repo"
        ) as game_ids_repo_cls, patch(
            "bot.handlers.cards.profile.make_report_keboard",
            side_effect=lambda *args, **kwargs: "kb",
        ), patch(
            "bot.handlers.cards.profile._edit_card_error",
            AsyncMock(),
        ) as edit_card_error:
            game_ids_repo_cls.return_value.get_active_UID = AsyncMock(
                return_value=SimpleNamespace(game_id="gid")
            )
            await handle_ccard(callback, db_session=None)

        edit_card_error.assert_awaited_once()
        callback.answer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()