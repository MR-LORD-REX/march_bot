import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from server.admin.panel.broadcast import validate_html


class BroadcastValidationTests(unittest.TestCase):
    def test_plain_text_is_not_validated(self):
        self.assertIsNone(validate_html("hello <world"))

    def test_supported_telegram_markup_is_allowed(self):
        self.assertIsNone(validate_html("<b>hello</b> <tg-spoiler>secret</tg-spoiler>"))
        self.assertIsNone(validate_html('<a href="https://example.com">link</a>'))
        self.assertIsNone(validate_html("<b>line<br>break</b>"))

    def test_unknown_tag_is_rejected(self):
        self.assertIn("unsupported tag", validate_html("<message>hello</message>"))

    def test_unclosed_tag_is_rejected(self):
        self.assertIn("unclosed tag", validate_html("<b>hello"))

    def test_mismatched_close_is_rejected(self):
        self.assertIn("unexpected closing", validate_html("<b>hello</i>"))


class BroadcastWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_starts_one_worker(self):
        import server.admin.panel.broadcast as module

        module._queue = None
        module._worker_task = None
        bot = SimpleNamespace(send_message=AsyncMock())
        with patch.object(module, "_worker", AsyncMock(side_effect=Exception("stop"))):
            await module.enqueue(1, bot)
            await module.enqueue(2, bot)
            self.assertEqual(module._get_queue().qsize(), 2)
            self.assertIsNotNone(module._worker_task)
            await module.stop_worker()

    async def test_stop_worker_is_idempotent(self):
        import server.admin.panel.broadcast as module

        module._worker_task = None
        await module.stop_worker()
        await module.stop_worker()


if __name__ == "__main__":
    unittest.main()