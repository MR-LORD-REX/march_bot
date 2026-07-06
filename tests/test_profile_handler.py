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
            answer=AsyncMock(),
            message=SimpleNamespace(
                edit_text=AsyncMock(),
                edit_media=AsyncMock(),
            ),
        )

        async def fake_image_to_tg_file(_):
            raise ValueError("missing card")

        with patch("bot.handlers.cards.profile.get_character_card", AsyncMock(return_value=CharRes(cached=False, card=None, data="1"))), \
             patch("bot.handlers.cards.profile.image_to_tgFile", side_effect=fake_image_to_tg_file), \
             patch("bot.handlers.cards.profile.GameIDs_repo") as game_ids_repo_cls, \
             patch("bot.handlers.cards.profile.make_back_kb", return_value="kb"), \
             patch("bot.handlers.cards.profile.make_report_keboard", side_effect=lambda *args, **kwargs: "kb"):
            game_ids_repo_cls.return_value.get_active_UID = AsyncMock(return_value=SimpleNamespace(game_id="gid"))
            await handle_ccard(callback, db_session=None)

        callback.message.edit_text.assert_awaited_once()
        callback.answer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
