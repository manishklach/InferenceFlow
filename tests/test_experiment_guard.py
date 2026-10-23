import unittest
from datetime import datetime, timezone, timedelta
import httpx
from scripts.experiment_guard import decision, terminate_verified


class GuardTests(unittest.TestCase):
    def test_time_and_budget_trigger_below_ten(self):
        start = datetime.now(timezone.utc)
        self.assertTrue(decision(start, start + timedelta(hours=2), ".351")["terminate"])
        self.assertTrue(decision(start, start + timedelta(hours=1), "8")["terminate"])
        self.assertFalse(decision(start, start + timedelta(minutes=1), ".351")["terminate"])
        with self.assertRaises(ValueError):
            decision(start, start, "NaN")

    def test_only_exact_owned_pod_and_fresh_delete_confirmation(self):
        calls = []
        deleted = False

        def respond(request):
            nonlocal deleted
            calls.append((request.method, request.url.path))
            if request.method == "DELETE":
                deleted = True
                return httpx.Response(204)
            return httpx.Response(404) if deleted else httpx.Response(200, json={"id": "exact", "name": "approved"})

        with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as c:
            with self.assertRaises(ValueError):
                terminate_verified(c, {"pod_id": "exact", "pod_name": "unrelated"})
            self.assertFalse(any(method == "DELETE" for method, path in calls))
            self.assertTrue(terminate_verified(c, {"pod_id": "exact", "pod_name": "approved"}))
            self.assertEqual(calls[-1], ("GET", "/pods/exact"))
