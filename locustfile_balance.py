from locust import HttpUser, SequentialTaskSet, between, task
import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("locust")

LOG_DIR = Path("/Users/souny-kks/Documents/DevSecOps/locust/logs")
ERROR_LOG_FILE = LOG_DIR / "balance-history-errors.log"
_error_log_lock = threading.Lock()

CUSTOMER_ID = 50
BILL_HISTORY_PAGE = 1
BILL_HISTORY_LIMIT = 10

ENDPOINTS = {
    "point_balance": "/app/api/v1/loyalty/balance/{customer_id}",
    "bill_history": "/app/api/v1/bill-history/list?limit=10&cursor=0",
}


class BalanceHistoryTasks(SequentialTaskSet):
    """Workflow: get point balance → get bill history."""

    def on_start(self):
        self.ctx = {}
        self._iteration_count = 0

    def on_iteration_start(self):
        self.ctx = {}

    def get_next_task(self):
        task = super().get_next_task()
        if task == self.tasks[0]:
            if self._iteration_count > 0:
                self.on_iteration_start()
            self._iteration_count += 1
        return task

    def _write_error_log(self, line):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _error_log_lock:
            with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} {line}\n")

    def _log_step_error(self, step_name, message, **details):
        parts = [f"{step_name}: {message}"]
        for key, value in details.items():
            parts.append(f"{key}={value}")
        if self.ctx:
            parts.append(f"ctx={self.ctx}")
        line = " | ".join(parts)
        logger.error(line)
        self._write_error_log(line)

    def _assert_ok(self, response, step_name, expected_status=200):
        if response.status_code != expected_status:
            self._log_step_error(
                step_name,
                "HTTP request failed",
                status=response.status_code,
                response=response.text,
            )
            self.interrupt()
            return False
        return True

    def _assert_api_status(self, body, step_name):
        if not body.get("status"):
            self._log_step_error(step_name, "API returned status=false", body=body)
            self.interrupt()
            return False
        return True

    @task
    def step1_get_point_balance(self):
        name = ENDPOINTS["point_balance"].format(customer_id=CUSTOMER_ID)
        response = self.client.get(name, name=name)
        if not self._assert_ok(response, "Step 1: Get Point Balance"):
            return
        body = response.json()
        if not self._assert_api_status(body, "Step 1: Get Point Balance"):
            return
        data = body.get("data", {})
        self.ctx["customer_id"] = CUSTOMER_ID
        self.ctx["point_balance"] = data.get("balance") or data.get("point") or data
        logger.info(
            "[Step 1] Point balance: customer_id=%s balance=%s",
            CUSTOMER_ID,
            self.ctx["point_balance"],
        )

    @task
    def step2_get_bill_history(self):
        name = ENDPOINTS["bill_history"]
        params = {"page": BILL_HISTORY_PAGE, "limit": BILL_HISTORY_LIMIT}
        response = self.client.get(name, params=params, name=name)
        if not self._assert_ok(response, "Step 2: Get Bill History"):
            return
        body = response.json()
        if not self._assert_api_status(body, "Step 2: Get Bill History"):
            return
        data = body.get("data", {})
        items = data if isinstance(data, list) else data.get("items") or data.get("list") or []
        self.ctx["bill_count"] = len(items) if isinstance(items, list) else data.get("total")
        logger.info(
            "[Step 2] Bill history: page=%s limit=%s count=%s",
            BILL_HISTORY_PAGE,
            BILL_HISTORY_LIMIT,
            self.ctx["bill_count"],
        )


class BalanceHistoryUser(HttpUser):
    wait_time = between(1, 2)
    tasks = [BalanceHistoryTasks]
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.nC3om-pg2ETd4pY1qJJhn-_jeqm4qOsGlcYieVIwG0hnqt8jgCg1p_BXjrXZgdNPZkHeFiyv5DCv0BDE6zIQrSwySz-wVTZFbZskqcUZB3CYLbC476QiUyHchKfyouSG3sgJPqhj2ADT3bgVmT58-mHkrj0lsQ.xDFaE98vaegSJQD4n-pfGMSA-XeIGy7ja7mW3XsOyYQ"

    def on_start(self):
        self.client.headers = {"Authorization": f"Bearer {self.token}"}
