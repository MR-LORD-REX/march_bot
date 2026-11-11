import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.DB.models.reports import Report
from bot.services.reports.workflow import (
    _reply_text,
    create_or_get_report,
    deliver_reply,
    notify_report_created,
)


class ReportWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_or_get_report_reuses_open_report(self):
        existing = Report(
            id=7,
            reporter_id=42,
            report_type="PFP",
            uid=100,
            status="open",
        )
        session = SimpleNamespace()
        with patch(
            "bot.services.reports.workflow.ReportRepo"
        ) as repo_cls, patch(
            "bot.services.reports.workflow.UserRepo"
        ) as user_repo_cls:
            repo_cls.return_value.get_open_for_origin = AsyncMock(return_value=existing)
            report, created = await create_or_get_report(
                session,
                SimpleNamespace(),
                reporter_id=42,
                report_type="PFP",
                uid=100,
                origin_chat_id=-1,
                origin_message_id=2,
            )

        self.assertIs(report, existing)
        self.assertFalse(created)
        repo_cls.return_value.create.assert_not_called()

    async def test_reply_text_mentions_reporter_and_escapes_body(self):
        report = Report(
            id=9,
            reporter_id=42,
            report_type="PFP",
            uid=100,
            status="open",
        )
        reporter = SimpleNamespace(
            telegram_id=42,
            username="trailblazer",
            display_name="<Trailblazer>",
        )
        text = _reply_text(report, reporter, "<b>fixed</b> & done")

        self.assertIn('href="tg://user?id=42"', text)
        self.assertIn("&lt;Trailblazer&gt;", text)
        self.assertIn("&lt;b&gt;fixed&lt;/b&gt; &amp; done", text)

    async def test_deliver_reply_tags_reporter_and_records_message(self):
        report = Report(
            id=9,
            reporter_id=42,
            report_type="PFP",
            uid=100,
            status="open",
            origin_chat_id=-100,
            origin_message_id=11,
        )
        session = SimpleNamespace()
        sent = SimpleNamespace(
            chat=SimpleNamespace(id=-100),
            message_id=12,
        )
        bot = SimpleNamespace(send_message=AsyncMock(return_value=sent))
        reporter = SimpleNamespace(
            telegram_id=42,
            username="trailblazer",
            display_name="Trailblazer",
        )
        with patch(
            "bot.services.reports.workflow.UserRepo"
        ) as user_repo_cls, patch(
            "bot.services.reports.workflow.ReportRepo"
        ) as repo_cls:
            user_repo_cls.return_value.get_by_tele_id = AsyncMock(return_value=reporter)
            repo_cls.return_value.add_message = AsyncMock()
            repo_cls.return_value.add_event = AsyncMock()

            delivered = await deliver_reply(session, bot, report, 7, "fixed")

        self.assertTrue(delivered)
        kwargs = bot.send_message.await_args.kwargs
        self.assertEqual(kwargs["parse_mode"], "HTML")
        self.assertEqual(kwargs["reply_to_message_id"], 11)
        self.assertIn("tg://user?id=42", kwargs["text"])
        repo_cls.return_value.add_message.assert_awaited_once()
        self.assertTrue(
            repo_cls.return_value.add_message.await_args.kwargs["delivered"]
        )

    async def test_deliver_reply_falls_back_to_dm_when_origin_fails(self):
        report = Report(
            id=10,
            reporter_id=42,
            report_type="PFP",
            uid=100,
            status="open",
            origin_chat_id=-100,
            origin_message_id=11,
        )
        session = SimpleNamespace()
        sent = SimpleNamespace(
            chat=SimpleNamespace(id=42),
            message_id=13,
        )
        bot = SimpleNamespace(
            send_message=AsyncMock(side_effect=[RuntimeError("message deleted"), sent])
        )
        reporter = SimpleNamespace(
            telegram_id=42,
            username="trailblazer",
            display_name="Trailblazer",
        )
        with patch(
            "bot.services.reports.workflow.UserRepo"
        ) as user_repo_cls, patch(
            "bot.services.reports.workflow.ReportRepo"
        ) as repo_cls:
            user_repo_cls.return_value.get_by_tele_id = AsyncMock(return_value=reporter)
            repo_cls.return_value.add_message = AsyncMock()
            repo_cls.return_value.add_event = AsyncMock()

            delivered = await deliver_reply(session, bot, report, 7, "fixed")

        self.assertTrue(delivered)
        self.assertEqual(bot.send_message.await_count, 2)
        first_call, second_call = bot.send_message.await_args_list
        self.assertEqual(first_call.kwargs["chat_id"], -100)
        self.assertEqual(first_call.kwargs["reply_to_message_id"], 11)
        self.assertTrue(first_call.kwargs["allow_sending_without_reply"])
        self.assertEqual(second_call.kwargs["chat_id"], 42)
        self.assertNotIn("reply_to_message_id", second_call.kwargs)
        self.assertTrue(
            repo_cls.return_value.add_message.await_args.kwargs["delivered"]
        )
    async def test_notify_report_created_records_admin_message(self):
        report = Report(
            id=11,
            reporter_id=42,
            report_type="PFP",
            uid=100,
            status="open",
        )
        session = SimpleNamespace()
        sent = SimpleNamespace(
            chat=SimpleNamespace(id=-100),
            message_id=77,
        )
        bot = SimpleNamespace(send_message=AsyncMock(return_value=sent))
        reporter = SimpleNamespace(
            telegram_id=42,
            username="trailblazer",
            display_name="Trailblazer",
        )
        with patch(
            "bot.services.reports.workflow.UserRepo"
        ) as user_repo_cls, patch(
            "bot.services.reports.workflow.ReportRepo"
        ) as repo_cls:
            user_repo_cls.return_value.get_by_tele_id = AsyncMock(return_value=reporter)
            repo_cls.return_value.set_admin_message = AsyncMock()
            repo_cls.return_value.add_event = AsyncMock()

            await notify_report_created(session, bot, report)

        repo_cls.return_value.set_admin_message.assert_awaited_once_with(report, -100, 77)
        repo_cls.return_value.add_event.assert_awaited_once_with(
            report.id, None, "admin_notified"
        )

if __name__ == "__main__":
    unittest.main()