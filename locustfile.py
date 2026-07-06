from locust import HttpUser, SequentialTaskSet, between, task
import logging
import random
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("locust")

LOG_DIR = Path(__file__).resolve().parent / "logs"
ERROR_LOG_FILE = LOG_DIR / "workflow-errors.log"
_error_log_lock = threading.Lock()

PHONE = "02056677603"
CUSTOMER_ID = 50
BCEL_CALLBACK_API_KEY = "ZoiPCydmGh7vsVKGPLBfUZ9E"
LOTTO_DRAW_COUNT_MIN = 10
LOTTO_DRAW_COUNT_MAX = 30

# /api/v1/sell/simulate/db
# /api/v1/sell/simulate

ENDPOINTS = {
    "lot_active": "/app/api/v1/lot/active-lot",
    # "create_bill": "/app-sell/api/v3/customer/oauth/draw/create",
    "create_bill": "/app-sell/api/v1/sell/simulate",
    "bill_detail": "/app/api/v1/bill-history/detail/{bill_id}",
    "bcel_callback": "/callback/api/v1/bcel/callback",
}


def _random_lotto_digit():
    length = random.randint(2, 6)
    return str(random.randint(10 ** (length - 1), 10 ** length - 1))


class SellWorkflowTasks(SequentialTaskSet):
    """Workflow: active lot → create bill → BCEL callback → bill detail."""

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
            response.failure(f"HTTP {response.status_code}")
            self.interrupt()
            return False
        return True

    def _assert_api_status(self, response, body, step_name):
        if not body.get("status"):
            self._log_step_error(step_name, "API returned status=false", body=body)
            response.failure("API status=false")
            self.interrupt()
            return False
        return True

    @task
    def step_get_lot_active(self):
        name = ENDPOINTS["lot_active"]
        with self.client.get(name, name=name, catch_response=True) as response:
            if not self._assert_ok(response, "Get Lot Active"):
                return
            body = response.json()
            if not self._assert_api_status(response, body, "Get Lot Active"):
                return
            data = body.get("data", {})
            lot_id = data.get("id")
            if lot_id is None:
                self._log_step_error("Get Lot Active", "active lot missing id", data=data)
                response.failure("active lot missing id")
                self.interrupt()
                return
            self.ctx["lot_id"] = lot_id
            self.ctx["doi_id"] = lot_id
            self.ctx["lot_name"] = data.get("int_name")
            self.ctx["start_datetime"] = data.get("start_datetime")
            self.ctx["end_datetime"] = data.get("end_datetime")
            response.success()

    @task
    def step1_create_bill(self):
        doi_id = self.ctx.get("doi_id")
        if doi_id is None:
            self._log_step_error("Step 1: Create Bill", "doi_id missing from active lot step")
            self.interrupt()
            return

        name = ENDPOINTS["create_bill"]
        random_price = [1000, 2000, 5000, 10000, 25000]
        digits = set()
        target_count = random.randint(LOTTO_DRAW_COUNT_MIN, LOTTO_DRAW_COUNT_MAX)
        while len(digits) < target_count:
            digits.add(_random_lotto_digit())
        lotto_draw_number = [
            {"digit": d, "money": random.choice(random_price)} for d in digits
        ]
        payload = {
            "phone": PHONE,
            "doi_id": doi_id,
            "lotto_draw_number": lotto_draw_number,
            "mute_lotto": [{"id": 0}],
            "payment_request": {
                "draw_id": 26103,
                "bill_id": None,
                "payment_link_id": None,
                "payment_method_id": 4,
                "customer_account": PHONE,
                "account_type": None,
                "use_point": False,
            },
        }
        with self.client.post(name, json=payload, name=name, catch_response=True) as response:
            if not self._assert_ok(response, "Step 1: Create Bill"):
                return
            body = response.json()
            if not self._assert_api_status(response, body, "Step 1: Create Bill"):
                return
            data = body.get("data", {})
            bill_id = data.get("bill_id")
            ticket_id = data.get("ticket_id")
            if not bill_id or not ticket_id:
                self._log_step_error(
                    "Step 1: Create Bill",
                    "bill_id or ticket_id missing in response",
                    data=data,
                )
                response.failure("bill_id or ticket_id missing")
                self.interrupt()
                return
            self.ctx["bill_id"] = bill_id
            self.ctx["ticket_id"] = ticket_id
            response.success()

    @task
    def step2_bcel_callback(self):
        ticket_id = self.ctx.get("ticket_id")
        if not ticket_id:
            self._log_step_error("Step 2: BCEL Callback", "ticket_id missing for BCEL callback")
            self.interrupt()
            return

        callback_name = ENDPOINTS["bcel_callback"]
        callback_payload = {"ticket_id": ticket_id}
        callback_headers = {"x-api-key": BCEL_CALLBACK_API_KEY}
        auth_header = self.client.headers.pop("Authorization", None)
        try:
            with self.client.post(
                callback_name,
                json=callback_payload,
                headers=callback_headers,
                name=callback_name,
                catch_response=True,
            ) as callback_response:
                if not self._assert_ok(callback_response, "Step 2: BCEL Callback"):
                    return
                callback_response.success()
        finally:
            if auth_header is not None:
                self.client.headers["Authorization"] = auth_header

    @task
    def step3_get_bill_detail(self):
        bill_id = self.ctx.get("bill_id")
        if not bill_id:
            self._log_step_error("Step 3: Get Bill Detail", "bill_id missing from step 1")
            self.interrupt()
            return
        name = ENDPOINTS["bill_detail"].format(bill_id=bill_id)
        with self.client.get(name, name=name, catch_response=True) as response:
            if not self._assert_ok(response, "Step 3: Get Bill Detail"):
                return
            body = response.json()
            if body.get("status") is not None and not self._assert_api_status(
                response, body, "Step 3: Get Bill Detail"
            ):
                return
            data = body.get("data", body)
            self.ctx["ticket_id"] = data.get("ticket_id") or self.ctx.get("ticket_id")
            self.ctx["total_amount"] = data.get("total_amount")
            self.ctx["bill_status_name"] = data.get("bill_status_name")
            response.success()

class SellWorkflowUser(HttpUser):
    wait_time = between(1, 2)
    tasks = [SellWorkflowTasks]
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.nC3om-pg2ETd4pY1qJJhn-_jeqm4qOsGlcYieVIwG0hnqt8jgCg1p_BXjrXZgdNPZkHeFiyv5DCv0BDE6zIQrSwySz-wVTZFbZskqcUZB3CYLbC476QiUyHchKfyouSG3sgJPqhj2ADT3bgVmT58-mHkrj0lsQ.xDFaE98vaegSJQD4n-pfGMSA-XeIGy7ja7mW3XsOyYQ"

    def on_start(self):
        self.client.headers = {"Authorization": f"Bearer {self.token}"}
