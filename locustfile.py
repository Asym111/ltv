from locust import HttpUser, task, between
import random

class LTVLoadTest(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        """Логинимся перед тестом."""
        self.client.post("/auth", data={
            "phone": "77001234567",
            "password": "admin123",
        })

    @task(5)
    def health(self):
        self.client.get("/health")

    @task(2)
    def transactions_list(self):
        self.client.get("/api/transactions/?limit=10")

    @task(1)
    def users_list(self):
        self.client.get("/api/users/")