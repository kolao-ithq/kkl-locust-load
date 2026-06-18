from locust import HttpUser, SequentialTaskSet, between, task
import logging
import random
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("locust")

LOG_DIR = Path("/Users/souny-kks/Documents/DevSecOps/locust/logs")
ERROR_LOG_FILE = LOG_DIR / "workflow-errors.log"
_error_log_lock = threading.Lock()

PHONE = "02056677603"
CUSTOMER_ID = 50
BCEL_CALLBACK_API_KEY = "ZoiPCydmGh7vsVKGPLBfUZ9E"

ENDPOINTS = {
    "lot_active": "/app/api/v1/lot/active-lot",
    # "create_bill": "/app-sell/api/v3/customer/oauth/draw/create",
    "create_bill": "/app-sell/api/v1/sell/simulate",
    "bill_detail": "/app/api/v1/bill-history/detail/{bill_id}",
    "bcel_callback": "/callback/api/v1/bcel/callback/test",
}


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
    def step_get_lot_active(self):
        name = ENDPOINTS["lot_active"]
        response = self.client.get(name, name=name)
        if not self._assert_ok(response, "Get Lot Active"):
            return
        body = response.json()
        if not self._assert_api_status(body, "Get Lot Active"):
            return
        data = body.get("data", {})
        lot_id = data.get("id")
        if lot_id is None:
            self._log_step_error("Get Lot Active", "active lot missing id", data=data)
            self.interrupt()
            return
        self.ctx["lot_id"] = lot_id
        self.ctx["doi_id"] = lot_id
        self.ctx["lot_name"] = data.get("int_name")
        self.ctx["start_datetime"] = data.get("start_datetime")
        self.ctx["end_datetime"] = data.get("end_datetime")
        logger.info("[Get Lot Active] id=%s name=%s", lot_id, self.ctx["lot_name"])

    @task
    def step1_create_bill(self):
        name = ENDPOINTS["create_bill"]
        random_digit = [27, 67, 127, 167, 227, 267, 327, 367, 427, 467, 527, 567, 627, 667, 727, 767, 827, 867, 927, 967, 17, 57, 36, 76, 40, 80]
        random_price = [1000, 2000]
        lotto_draw_number = [
            {"digit": str(d), "money": random.choice(random_price)}
            for d in random.sample(random_digit, random.randint(1, 3))
        ]
        payload = {
            "phone": PHONE,
            "doi_id": self.ctx.get("doi_id"),
            "lotto_draw_number": lotto_draw_number,
            "mute_lotto": [{"id": 0}],
            "payment_request": {
                "draw_id": 26091,
                "bill_id": None,
                "payment_link_id": None,
                "payment_method_id": 4,
                "customer_account": PHONE,
                "account_type": None,
                "use_point": False,
            },
        }
        response = self.client.post(name, json=payload, name=name)
        if not self._assert_ok(response, "Step 1: Create Bill"):
            return
        body = response.json()
        if not self._assert_api_status(body, "Step 1: Create Bill"):
            return
        data = body.get("data", {})
        self.ctx["bill_id"] = data.get("bill_id")
        self.ctx["ticket_id"] = data.get("ticket_id")
        logger.info(
            "[Step 1] Bill created: bill_id=%s ticket_id=%s lotto_draw_number=%s",
            self.ctx["bill_id"],
            self.ctx["ticket_id"],
            lotto_draw_number,
        )

    @task
    def step2_bcel_callback(self):
        ticket_id = self.ctx.get("ticket_id")
        if not ticket_id:
            self._log_step_error("Step 2: BCEL Callback", "ticket_id missing for BCEL callback")
            self.interrupt()
            return

        callback_name = ENDPOINTS["bcel_callback"]
        callback_payload = {"ticket_id": ticket_id, "is_from_test": True}
        callback_headers = {"x-api-key": BCEL_CALLBACK_API_KEY}
        auth_header = self.client.headers.pop("Authorization", None)
        try:
            callback_response = self.client.post(
                callback_name, json=callback_payload, headers=callback_headers, name=callback_name
            )
        finally:
            if auth_header is not None:
                self.client.headers["Authorization"] = auth_header
        if not self._assert_ok(callback_response, "Step 2: BCEL Callback"):
            return
        logger.info("[Step 2] BCEL callback: ticket_id=%s response=%s", ticket_id, callback_response.text)

    @task
    def step3_get_bill_detail(self):
        bill_id = self.ctx.get("bill_id")
        if not bill_id:
            self._log_step_error("Step 3: Get Bill Detail", "bill_id missing from step 1")
            self.interrupt()
            return
        name = ENDPOINTS["bill_detail"].format(bill_id=bill_id)
        response = self.client.get(name, name=name)
        if not self._assert_ok(response, "Step 3: Get Bill Detail"):
            return
        body = response.json()
        if body.get("status") is not None and not self._assert_api_status(body, "Step 3: Get Bill Detail"):
            return
        data = body.get("data", body)
        self.ctx["ticket_id"] = data.get("ticket_id") or self.ctx.get("ticket_id")
        self.ctx["total_amount"] = data.get("total_amount")
        self.ctx["bill_status_name"] = data.get("bill_status_name")
        logger.info(
            "[Step 3] Bill detail: bill_id=%s ticket_id=%s status=%s amount=%s",
            bill_id,
            data.get("ticket_id"),
            data.get("bill_status_name"),
            data.get("total_amount"),
        )

class SellWorkflowUser(HttpUser):
    wait_time = between(1, 2)
    tasks = [SellWorkflowTasks]
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.nC3om-pg2ETd4pY1qJJhn-_jeqm4qOsGlcYieVIwG0hnqt8jgCg1p_BXjrXZgdNPZkHeFiyv5DCv0BDE6zIQrSwySz-wVTZFbZskqcUZB3CYLbC476QiUyHchKfyouSG3sgJPqhj2ADT3bgVmT58-mHkrj0lsQ.xDFaE98vaegSJQD4n-pfGMSA-XeIGy7ja7mW3XsOyYQ"

    def on_start(self):
        self.client.headers = {"Authorization": f"Bearer {self.token}"}
