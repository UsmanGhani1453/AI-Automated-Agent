"""
Executor: runs a single plan step with retry + graceful failure recording,
so one bad step (e.g. an SMTP hiccup) doesn't crash the whole run.
"""
import time
from app.database.database import get_conn, now, dumps


class StepFailure(Exception):
    def __init__(self, step, error):
        self.step = step
        self.error = error
        super().__init__(f"Step '{step}' failed: {error}")


class Executor:
    def __init__(self, max_retries=2, retry_delay_seconds=1):
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def run_step(self, task_id, step_name, fn, *args, **kwargs):
        last_error = None
        for attempt in range(1, self.max_retries + 2):
            try:
                result = fn(*args, **kwargs)
                self._log(task_id, step_name, "success", None)
                return result
            except Exception as e:
                last_error = str(e)
                self._log(task_id, step_name, "retried" if attempt <= self.max_retries else "failed", last_error)
                if attempt <= self.max_retries:
                    time.sleep(self.retry_delay_seconds)
                    continue
        raise StepFailure(step_name, last_error)

    def _log(self, task_id, step_name, status, error):
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO actions (task_id, action_type, status, error, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (task_id, step_name, status, error, now()),
            )
