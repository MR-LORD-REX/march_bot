from typing import Callable, Awaitable, Any, Optional

from enum import Enum, auto
from datetime import datetime, timedelta, timezone
import asyncio
import logging
import random

from bot.DB.repo.scheduler_repo import SchedulerRepo


TaskFunc = Callable[..., Awaitable[Any]]
DailyTime = tuple[int, int, int]  # (HH, MM, SS)
WeeklySchedule = dict[str, tuple[int, int]]  # {"Monday": (10, 30)}

logger = logging.getLogger(__name__)

class TaskType(Enum):
    Oneshot = auto()
    Interval = auto()
    Daily = auto()
    Weekly = auto()


class Task:
    def __init__(
        self,
        task_id: str,
        task_name: str,
        coro: TaskFunc,
        task_type: TaskType = TaskType.Oneshot,
        interval: int = 0,
        delay: int = 0,
        max_errors: int = 3,
        daily_at: Optional[DailyTime] = None,
        weekly_schedule: Optional[WeeklySchedule] = None,
        coro_args: tuple = (),
        coro_kwargs: dict = None,
    ):
        self.task_id = task_id
        self.task_name = task_name
        self.coro = coro
        self.max_errors = max_errors
        self.task_type = task_type
        self.interval = interval
        self.delay = delay
        self.daily_at = daily_at
        self.weekly_schedule = weekly_schedule
        self.coro_args = coro_args
        self.coro_kwargs = coro_kwargs or {}
        self.cancelled = False
        self.asyncio_task: Optional[asyncio.Task] = None

    @property
    def running(self) -> bool:
        return self.asyncio_task is not None and not self.asyncio_task.done()

    def cancel(self) -> None:
        self.cancelled = True
        if self.asyncio_task and not self.asyncio_task.done():
            self.asyncio_task.cancel()


class Scheduler:
    def __init__(self) -> None:
        self.all_tasks: dict[str, Task] = {}
        
    def get_task(self, task_id: str) -> Optional[Task]:
        return self.all_tasks.get(task_id)

    def _make_task(
        self,
        task_id: str,
        task_name: str,
        coro: TaskFunc,
        task_type: TaskType,
        interval: int = 0,
        delay: int = 0,
        max_errors: int = 3,
        daily_at: Optional[DailyTime] = None,
        weekly_schedule: Optional[WeeklySchedule] = None,
        args: tuple = (),
        kwargs: dict = None,
    ) -> Task:
        if task_id in self.all_tasks:
            msg = f"Task ID '{task_id}' already exists. Cancel it first or use a different ID."
            raise ValueError(msg)
        
        task = Task(
            task_id=task_id,
            task_name=task_name,
            coro=coro,
            task_type=task_type,
            interval=interval,
            delay=delay,
            max_errors=max_errors,
            daily_at=daily_at,
            weekly_schedule=weekly_schedule,
            coro_args=args,
            coro_kwargs=kwargs or {},
        )
        task.asyncio_task = asyncio.create_task(self._runner(task))
        self.all_tasks[task_id] = task
        return task

    def add_oneshot(
        self,
        task_id: str,
        task_name: str,
        coro: TaskFunc,
        delay: int = 0,
        max_errors: int = 3,
        *args,
        **kwargs,
    ) -> str:
        task = self._make_task(
            task_id,
            task_name,
            coro,
            TaskType.Oneshot,
            delay=delay,
            max_errors=max_errors,
            args=args,
            kwargs=kwargs,
        )
        return task.task_id

    def add_interval(
        self,
        task_id: str,
        task_name: str,
        coro: TaskFunc,
        interval: int,
        delay: int = 0,
        max_errors: int = 3,
        *args,
        **kwargs,
    ) -> str:
        task = self._make_task(
            task_id,
            task_name,
            coro,
            TaskType.Interval,
            interval=interval,
            delay=delay,
            max_errors=max_errors,
            args=args,
            kwargs=kwargs,
        )
        return task.task_id

    def add_daily(
        self,
        task_id: str,
        task_name: str,
        coro: TaskFunc,
        daily_at: DailyTime,
        delay: int = 0,
        max_errors: int = 3,
        *args,
        **kwargs,
    ) -> str:
        """Schedule a task to run daily at a specific time (UTC)."""
        task = self._make_task(
            task_id,
            task_name,
            coro,
            TaskType.Daily,
            delay=delay,
            max_errors=max_errors,
            daily_at=daily_at,
            args=args,
            kwargs=kwargs,
        )
        return task.task_id

    def add_weekly(
        self,
        task_id: str,
        task_name: str,
        coro: TaskFunc,
        weekly_schedule: WeeklySchedule,
        delay: int = 0,
        max_errors: int = 3,
        *args,
        **kwargs,
    ) -> str:
        """Schedule a task to run on specific days at specific times (UTC).
        
        Args:
            task_id: Unique task identifier (format: name_teleid)
            task_name: Name of the task
            coro: Coroutine to execute
            weekly_schedule: Dict mapping day names to (HH, MM) tuples.
                Example: {"Monday": (10, 30), "Friday": (16, 45)}
                Valid days: Monday-Sunday
            delay: Delay before first execution
            max_errors: Maximum errors before stopping
        """
        task = self._make_task(
            task_id,
            task_name,
            coro,
            TaskType.Weekly,
            delay=delay,
            max_errors=max_errors,
            weekly_schedule=weekly_schedule,
            args=args,
            kwargs=kwargs,
        )
        return task.task_id

    def cancel_task(self, task_id: str) -> bool:
        task = self.all_tasks.get(task_id)
        if not task:
            return False
        task.cancel()
        return True

    @staticmethod
    def _day_name_to_weekday(day_name: str) -> int:
        """Convert day name to weekday number (0=Monday, 6=Sunday)."""
        days = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        day_lower = day_name.lower()
        if day_lower not in days:
            msg = f"Invalid day name: {day_name}. Must be Monday-Sunday"
            raise ValueError(msg)
        return days[day_lower]

    @staticmethod
    def _get_next_weekly_occurrence(
        now: datetime, weekly_schedule: WeeklySchedule
    ) -> tuple[datetime, str]:
        """Get the next occurrence of a weekly scheduled task.
        
        Returns:
            Tuple of (next_datetime, day_name)
        """
        next_occurrence = None
        next_day_name = None
        
        for day_name, (hour, minute) in weekly_schedule.items():
            target_weekday = Scheduler._day_name_to_weekday(day_name)
            target_time = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            
            current_weekday = now.weekday()
            days_ahead = (target_weekday - current_weekday) % 7
            
            if days_ahead == 0 and target_time <= now:
                days_ahead = 7
            
            target_time += timedelta(days=days_ahead)
            
            if next_occurrence is None or target_time < next_occurrence:
                next_occurrence = target_time
                next_day_name = day_name
        
        return next_occurrence, next_day_name

    async def _runner(self, task: Task) -> None:
        errors = 0
        first_run = True

        try:
            while True:
                if task.cancelled:
                    break

                if task.task_type == TaskType.Daily:
                    now = datetime.now(tz=timezone.utc)
                    target = now.replace(
                        hour=task.daily_at[0],
                        minute=task.daily_at[1],
                        second=task.daily_at[2],
                        microsecond=0,
                    )
                    if target <= now:
                        target += timedelta(days=1)
                    await asyncio.sleep((target - now).total_seconds())

                elif task.task_type == TaskType.Weekly:
                    now = datetime.now(tz=timezone.utc)
                    target, _ = self._get_next_weekly_occurrence(
                        now, task.weekly_schedule
                    )
                    await asyncio.sleep((target - now).total_seconds())

                elif first_run and task.delay > 0:
                    await asyncio.sleep(task.delay)

                first_run = False

                try:
                    await task.coro(*task.coro_args, **task.coro_kwargs)
                    errors = 0  
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    errors += 1
                    logger.warning(
                        f"Task {task.task_name} ({task.task_id}) "
                        f"error {errors}/{task.max_errors}: {e}"
                    )
                    if errors >= task.max_errors:
                        logger.error(
                            f"Task {task.task_name} ({task.task_id}) "
                            f"exceeded max errors, stopping"
                        )
                        break
                    await asyncio.sleep(random.randint(60, 120))
                    continue

                if task.task_type == TaskType.Oneshot:
                    break
                elif task.task_type == TaskType.Interval:
                    await asyncio.sleep(task.interval)
                elif task.task_type == TaskType.Daily:
                    now = datetime.now(tz=timezone.utc)
                    target = now.replace(
                        hour=task.daily_at[0],
                        minute=task.daily_at[1],
                        second=task.daily_at[2],
                        microsecond=0,
                    )
                    target += timedelta(days=1)
                    await asyncio.sleep((target - now).total_seconds())
                elif task.task_type == TaskType.Weekly:
                    now = datetime.now(tz=timezone.utc)
                    target, _ = self._get_next_weekly_occurrence(
                        now, task.weekly_schedule
                    )
                    await asyncio.sleep((target - now).total_seconds())

        except asyncio.CancelledError:
            logger.info(
                f"Task {task.task_name} ({task.task_id}) was cancelled"
            )
        finally:
            self.all_tasks.pop(task.task_id, None)
            logger.info(f"Task {task.task_id} process completed")
            
async def scheduled_tasks_on_startup():
    # for now it will only warn on startup to schedule again
    from bot.core.main import bot
    from bot.DB.asyncsessions import session_factory
    async with session_factory() as session:
        repo = SchedulerRepo(session)
        tasks_meta = await repo.get_all_tasks()
        for meta in tasks_meta:
            try:
                if meta.task_type == TaskType.Oneshot.name:
                    now=datetime.now(timezone.utc)
                    if meta.execution_time and meta.execution_time < now:
                        await repo.delete_task_meta(meta.task_id)
                        continue
                    else:
                        await bot.send_message(
                            chat_id=meta.user_id,
                            text=f"Your scheduled task '{meta.task_name}' was not executed while the bot was offline. Please schedule it again."
                        )
                        await repo.delete_task_meta(meta.task_id)
            except Exception as e:
                logger.error(f"Error while loading scheduled task {meta.task_id}: {e}")
                continue
                        