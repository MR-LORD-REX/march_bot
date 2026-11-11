import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from shared.runtime import BotRuntime
from shared.scheduling.scheduler import TaskType, scheduled_tasks_on_startup


class SchedulerStartupTests(unittest.IsolatedAsyncioTestCase):
    def _session(self):
        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        return Session()

    async def test_missed_oneshot_uses_bound_runtime_bot(self):
        meta = SimpleNamespace(
            task_id="task-1",
            task_name="Daily check",
            task_type=TaskType.Oneshot.name,
            execution_time=datetime.now(timezone.utc) + timedelta(minutes=5),
            user_id=42,
        )
        bot = SimpleNamespace(send_message=AsyncMock())
        repo = SimpleNamespace(
            get_all_tasks=AsyncMock(return_value=[meta]),
            delete_task_meta=AsyncMock(),
        )

        with patch(
            "DB.asyncsessions.session_factory", return_value=self._session()
        ), patch.object(
            BotRuntime, "bot", new_callable=lambda: property(lambda self: bot)
        ), patch(
            "shared.scheduling.scheduler.SchedulerRepo", return_value=repo
        ):
            await scheduled_tasks_on_startup()

        bot.send_message.assert_awaited_once()
        self.assertEqual(bot.send_message.await_args.kwargs["chat_id"], 42)
        repo.delete_task_meta.assert_awaited_once_with("task-1")

    async def test_failed_notification_does_not_abort_startup(self):
        metas = [
            SimpleNamespace(
                task_id="bad",
                task_name="Broken",
                task_type=TaskType.Oneshot.name,
                execution_time=datetime.now(timezone.utc) + timedelta(minutes=5),
                user_id=42,
            ),
            SimpleNamespace(
                task_id="expired",
                task_name="Expired",
                task_type=TaskType.Oneshot.name,
                execution_time=datetime.now(timezone.utc) - timedelta(minutes=5),
                user_id=43,
            ),
        ]
        bot = SimpleNamespace(
            send_message=AsyncMock(side_effect=RuntimeError("blocked"))
        )
        repo = SimpleNamespace(
            get_all_tasks=AsyncMock(return_value=metas),
            delete_task_meta=AsyncMock(),
        )

        with patch(
            "DB.asyncsessions.session_factory", return_value=self._session()
        ), patch.object(
            BotRuntime, "bot", new_callable=lambda: property(lambda self: bot)
        ), patch(
            "shared.scheduling.scheduler.SchedulerRepo", return_value=repo
        ):
            await scheduled_tasks_on_startup()

        self.assertEqual(bot.send_message.await_count, 1)
        repo.delete_task_meta.assert_awaited_once_with("expired")


if __name__ == "__main__":
    unittest.main()