from locust import HttpUser, SequentialTaskSet, between, task
import logging
import random

logger = logging.getLogger("locust")

PHONE = "02056677603"
CUSTOMER_ID = 50
BCEL_CALLBACK_API_KEY = "ZoiPCydmGh7vsVKGPLBfUZ9E"

ENDPOINTS = {
    "point_balance": f"/app/api/v1/loyalty/balance/{CUSTOMER_ID}",
    "lot_active": "/app/api/v1/lot/active-lot",
    "create_bill": "/app-sell/api/v3/customer/oauth/draw/create",
    "bill_pending_detail": "/app/api/v1/bill-history/detail/{bill_id}",
    "bill_finish_detail": "/app/api/v1/bill-history/detail/{bill_id}",
    "bcel_callback": "/callback/api/v1/bcel/callback",
    "bill_history": "/app/api/v1/bill-history/list",
}


class SellWorkflowTasks(SequentialTaskSet):
    """Workflow: point balance → active lot → create bill → pending detail → callback → finish detail → bill history."""

    def on_start(self):
        self.ctx = {}

    def _assert_ok(self, response, step_name, expected_status=200):
        if response.status_code != expected_status:
            logger.error("%s failed: status=%s response=%s", step_name, response.status_code, response.text)
            self.interrupt()
            return False
        return True

    def _assert_api_status(self, body, step_name):
        if not body.get("status"):
            logger.error("%s: API returned status=false: %s", step_name, body)
            self.interrupt()
            return False
        return True

    @task
    def step1_get_point_balance(self):
        name = ENDPOINTS["point_balance"]
        response = self.client.get(name, name=name)
        if not self._assert_ok(response, "Step 1: Get Point Balance"):
            return
        body = response.json()
        if not self._assert_api_status(body, "Step 1: Get Point Balance"):
            return
        data = body.get("data", {})
        self.ctx["customer_id"] = data.get("customer_id")
        self.ctx["point_balance"] = data.get("balance")
        logger.info("[Step 1] Point balance: %s", data)

    @task
    def step2_get_lot_active(self):
        name = ENDPOINTS["lot_active"]
        response = self.client.get(name, name=name)
        if not self._assert_ok(response, "Step 2: Get Lot Active"):
            return
        body = response.json()
        if not self._assert_api_status(body, "Step 2: Get Lot Active"):
            return
        data = body.get("data", {})
        lot_id = data.get("id")
        if lot_id is None:
            logger.error("Step 2: Active lot missing id: %s", data)
            self.interrupt()
            return
        self.ctx["lot_id"] = lot_id
        self.ctx["doi_id"] = lot_id
        self.ctx["lot_name"] = data.get("int_name")
        self.ctx["start_datetime"] = data.get("start_datetime")
        self.ctx["end_datetime"] = data.get("end_datetime")
        logger.info("[Step 2] Active lot: id=%s name=%s", lot_id, self.ctx["lot_name"])

    @task
    def step3_create_bill(self):
        name = ENDPOINTS["create_bill"]
        random_digit = [27, 67, 127, 167, 227, 267, 327, 367, 427, 467, 527, 567, 627, 667, 727, 767, 827, 867, 927, 967, 17, 57, 36, 76, 40, 80]
        random_price = [1000, 2000]
        lotto_draw_number = [
            {"digit": str(d), "money": random.choice(random_price)}
            for d in random.sample(random_digit, random.randint(1, 3))
        ]
        payload = {
            "phone": PHONE,
            "doi_id": self.ctx.get("lot_id"),
            "lotto_draw_number": lotto_draw_number,
            "mute_lotto": [{"id": 0}],
            "payment_request": {
                "bill_id": None,
                "payment_link_id": None,
                "payment_method_id": 4,
                "customer_account": PHONE,
                "account_type": None,
                "use_point": False,
            },
        }
        response = self.client.post(name, json=payload, name=name)
        if not self._assert_ok(response, "Step 3: Create Bill"):
            return
        body = response.json()
        if not self._assert_api_status(body, "Step 3: Create Bill"):
            return
        data = body.get("data", {})
        self.ctx["bill_id"] = data.get("bill_id")
        self.ctx["ticket_id"] = data.get("ticket_id")
        logger.info(
            "[Step 3] Bill created: bill_id=%s ticket_id=%s lotto_draw_number=%s",
            self.ctx["bill_id"],
            self.ctx["ticket_id"],
            lotto_draw_number,
        )

    @task
    def step4_get_bill_pending_detail(self):
        bill_id = self.ctx.get("bill_id")
        if not bill_id:
            logger.error("Step 4: bill_id missing from step3 create bill")
            self.interrupt()
            return
        name = ENDPOINTS["bill_pending_detail"].format(bill_id=bill_id)
        response = self.client.get(name, name=name)
        if not self._assert_ok(response, "Step 4: Get Bill Pending Detail"):
            return
        body = response.json()
        if not self._assert_api_status(body, "Step 4: Get Bill Pending Detail"):
            return
        data = body.get("data", {})
        if data.get("bill_status_name") != "pending" and data.get("bill_status") != 1:
            logger.error("Step 4: Bill is not pending: %s", data)
            self.interrupt()
            return
        self.ctx["ticket_id"] = data.get("ticket_id") or self.ctx.get("ticket_id")
        self.ctx["total_amount"] = data.get("total_amount")
        self.ctx["bill_status_name"] = data.get("bill_status_name")
        logger.info(
            "[Step 4] Bill pending detail: bill_id=%s ticket_id=%s status=%s amount=%s",
            bill_id,
            data.get("ticket_id"),
            data.get("bill_status_name"),
            data.get("total_amount"),
        )

    @task
    def step5_callback(self):
        ticket_id = self.ctx.get("ticket_id")
        if not ticket_id:
            logger.error("Step 5: ticket_id missing from previous steps")
            self.interrupt()
            return
        name = ENDPOINTS["bcel_callback"]
        payload = {"ticket_id": ticket_id}
        headers = {"x-api-key": BCEL_CALLBACK_API_KEY}
        response = self.client.post(name, json=payload, headers=headers, name=name)
        if not self._assert_ok(response, "Step 5: BCEL Callback"):
            return
        logger.info("[Step 5] BCEL callback: ticket_id=%s response=%s", ticket_id, response.text)

    @task
    def step6_get_bill_finish_detail(self):
        bill_id = self.ctx.get("bill_id")
        if not bill_id:
            logger.error("Step 6: bill_id missing from previous steps")
            self.interrupt()
            return
        name = ENDPOINTS["bill_finish_detail"].format(bill_id=bill_id)
        response = self.client.get(name, name=name)
        if not self._assert_ok(response, "Step 6: Get Bill Finish Detail"):
            return
        body = response.json()
        if body.get("status") is not None and not self._assert_api_status(body, "Step 6: Get Bill Finish Detail"):
            return
        data = body.get("data", body)
        if data.get("bill_status_name") != "finish":
            logger.error("Step 6: Bill is not finish: %s", data)
            self.interrupt()
            return
        self.ctx["bill_status_name"] = data.get("bill_status_name")
        self.ctx["total_amount"] = data.get("total_amount")
        logger.info(
            "[Step 6] Bill finish detail: bill_id=%s ticket_id=%s status=%s amount=%s",
            bill_id,
            data.get("ticket_id"),
            data.get("bill_status_name"),
            data.get("total_amount"),
        )

    @task
    def step7_get_bill_history(self):
        name = ENDPOINTS["bill_history"]
        response = self.client.get(
            name,
            params={"page": 1, "limit": 10},
            name=name,
        )
        if not self._assert_ok(response, "Step 7: Get Bill History"):
            return
        body = response.json()
        if not self._assert_api_status(body, "Step 7: Get Bill History"):
            return
        logger.info("[Step 7] Bill history: %s rows", body.get("data", {}).get("totalRows"))


class SellWorkflowUser(HttpUser):
    wait_time = between(1, 2)
    tasks = [SellWorkflowTasks]
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.nC3om-pg2ETd4pY1qJJhn-_jeqm4qOsGlcYieVIwG0hnqt8jgCg1p_BXjrXZgdNPZkHeFiyv5DCv0BDE6zIQrSwySz-wVTZFbZskqcUZB3CYLbC476QiUyHchKfyouSG3sgJPqhj2ADT3bgVmT58-mHkrj0lsQ.xDFaE98vaegSJQD4n-pfGMSA-XeIGy7ja7mW3XsOyYQ"

    def on_start(self):
        self.client.headers = {"Authorization": f"Bearer {self.token}"}
