from locust import HttpUser, task, between
import logging

logger = logging.getLogger("locust")

class SellWorkflowUser(HttpUser):
    wait_time = between(1, 2)
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dOF1JSeNECG4Dy-AoJomlTYBoc8BsV3Y92KjWJOWfn_s2fvK4-OIZXRZHGUeclQRKyKzZJmGieGWGJnH7cjAppUcYrKFtZGnZPTYKSMnqpqKuVQ9Wd6W6iRfDOrVWWArqyqitEu-xAhc-sD_jDg-kRIfuqVwvbrGH1QCdjWUhoicFFCvtjr4hLQ126bnh4wZwTUpTA.5I4keNj2ER2dMsSbQ4daNhKRRUyYOsjy-NWCOPi0qt8"

    def on_start(self):
        """Set up authentication headers for all requests"""
        self.client.headers = {"Authorization": f"Bearer {self.token}"}

    @task
    def sell_ticket(self):
        # Step 1: Sell
        sell_payload = {
                    "items": [
                        {
                            "digit": "27",
                            "amount": 2000
                        },
                        {
                            "digit": "67",
                            "amount": 2000
                        },
                        {
                            "digit": "127",
                            "amount": 2000
                        },
                        {
                            "digit": "167",
                            "amount": 2000
                        },
                        {
                            "digit": "0127",
                            "amount": 2000
                        },
                        {
                            "digit": "0167",
                            "amount": 2000
                        }
                    ]
                }
        sell_response = self.client.post("/api/v1/lotto/sale", json=sell_payload)
        print("from sell response: " + str(sell_response.json()))
        if sell_response.status_code != 201:
            print(f"Sell failed: {sell_response.status_code} - {sell_response.text}")
            return

        # Extract bill_id from sell response for payment payload
        response_data = sell_response.json().get("data", {})
        bill_id = response_data.get("id")
        if not bill_id:
            print(f"Failed to extract bill_id from sell response: {response_data}")
            return  # stop if bill_id is missing