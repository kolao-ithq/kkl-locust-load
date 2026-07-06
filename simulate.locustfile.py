from locust import HttpUser, between, task
import logging
import random
import threading
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("locust")

LOG_DIR = Path(__file__).resolve().parent / "logs"
ERROR_LOG_FILE = LOG_DIR / "simulate-errors.log"
_error_log_lock = threading.Lock()

CUSTOMER_ID = "02098926654"
LOTTO_DRAW_COUNT_MIN = 10
LOTTO_DRAW_COUNT_MAX = 30
AMOUNTS = [1000, 2000, 5000, 10000, 25000]

SELL_TICKET_ENDPOINT = "/api/sellTicket"


def _random_lotto_digit():
    length = random.randint(2, 6)
    return str(random.randint(10 ** (length - 1), 10 ** length - 1))


def _random_items():
    digits = set()
    target_count = random.randint(LOTTO_DRAW_COUNT_MIN, LOTTO_DRAW_COUNT_MAX)
    while len(digits) < target_count:
        digits.add(_random_lotto_digit())
    return [{"digit": d, "amount": random.choice(AMOUNTS)} for d in digits]


class SimulateSellUser(HttpUser):
    # host = "https://simulate.kolaogroup.la"
    host = "http://202.137.144.77:30016" # Public IP
    # host = "https://kklloadt.kokkokm.com" # ADC

    wait_time = between(1, 2)
    token = "sim.access.dealer01.1783307362"

    def on_start(self):
        self.client.headers = {"Authorization": f"Bearer {self.token}"}

    def _write_error_log(self, line):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _error_log_lock:
            with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} {line}\n")

    def _log_error(self, message, **details):
        parts = [message]
        for key, value in details.items():
            parts.append(f"{key}={value}")
        line = " | ".join(parts)
        logger.error(line)
        self._write_error_log(line)

    @task
    def sell_ticket(self):
        payload = {
            "clientrefno": str(uuid.uuid4()),
            "customerid": CUSTOMER_ID,
            "items": _random_items(),
        }
        with self.client.post(
            SELL_TICKET_ENDPOINT,
            json=payload,
            name=SELL_TICKET_ENDPOINT,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                self._log_error(
                    "Sell Ticket: HTTP request failed",
                    status=response.status_code,
                    response=response.text,
                )
                response.failure(f"HTTP {response.status_code}")
                return

            body = response.json()
            if body.get("status") != "ACTIVE":
                self._log_error(
                    "Sell Ticket: unexpected status",
                    status=body.get("status"),
                    body=body,
                )
                response.failure(f"status={body.get('status')}")
                return

            if not body.get("billNumber"):
                self._log_error("Sell Ticket: billNumber missing", body=body)
                response.failure("billNumber missing")
                return

            response.success()
