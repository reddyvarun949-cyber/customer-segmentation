"""Automated tests for the API. Run from the project root:

    python -m unittest discover -s backend -p "test_*.py" -v

They use Flask's built-in test client, so no server needs to be running.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app  # noqa: E402

# A very active customer: recent, frequent, big baskets, mostly app, few coupons.
LOYAL = {
    "recency_days": 4, "frequency": 35, "monetary": 60000, "avg_basket": 1714.29,
    "coupon_rate": 0.05, "app_share": 0.9, "category_variety": 7,
}
# Coupon on almost every small order.
DEAL = {
    "recency_days": 15, "frequency": 12, "monetary": 5400, "avg_basket": 450,
    "coupon_rate": 0.9, "app_share": 0.8, "category_variety": 3,
}
# Has not ordered for 10 months.
LAPSED = {
    "recency_days": 300, "frequency": 3, "monetary": 2100, "avg_basket": 700,
    "coupon_rate": 0.33, "app_share": 0.67, "category_variety": 2,
}


class SegmentationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def post(self, payload):
        return self.client.post("/api/segment", json=payload)

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")

    def test_segments_list(self):
        data = self.client.get("/api/segments").get_json()
        self.assertEqual(len(data["segments"]), 5)
        total = sum(s["customers"] for s in data["segments"])
        self.assertEqual(total, data["customers_clustered"])
        for s in data["segments"]:
            for key in ("id", "name", "description", "suggested_action", "customers", "medians"):
                self.assertIn(key, s)
        self.assertIn("recency_days", data["valid_ranges"])

    def test_valid_assignment(self):
        r = self.post(LOYAL)
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        for key in ("segment_id", "segment_name", "description", "suggested_action", "fit", "comparison"):
            self.assertIn(key, body)
        self.assertEqual(len(body["comparison"]), 7)
        print("\n  sample assignment:", body["segment_name"], body["fit"], body["distance_ratio"])

    def test_expected_segments(self):
        self.assertEqual(self.post(LOYAL).get_json()["segment_name"], "Loyal big spenders")
        self.assertEqual(self.post(DEAL).get_json()["segment_name"], "Deal seekers")
        self.assertEqual(self.post(LAPSED).get_json()["segment_name"], "Lapsed customers")

    def test_numbers_sent_as_text_are_accepted(self):
        r = self.post({**DEAL, "frequency": "12", "coupon_rate": "0.9"})
        self.assertEqual(r.status_code, 200)

    def test_missing_field(self):
        payload = dict(LOYAL)
        del payload["monetary"]
        r = self.post(payload)
        self.assertEqual(r.status_code, 422)
        self.assertIn("monetary", r.get_json()["fields"])

    def test_not_a_number(self):
        r = self.post({**LOYAL, "frequency": "many"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.get_json()["fields"]["frequency"], "Must be a number.")

    def test_boolean_is_not_a_number(self):
        r = self.post({**LOYAL, "coupon_rate": True})
        self.assertEqual(r.status_code, 422)

    def test_rate_out_of_range(self):
        r = self.post({**LOYAL, "coupon_rate": 1.5})
        self.assertEqual(r.status_code, 422)
        self.assertIn("between", r.get_json()["fields"]["coupon_rate"])

    def test_negative_recency(self):
        r = self.post({**LOYAL, "recency_days": -3})
        self.assertEqual(r.status_code, 422)

    def test_whole_number_rule(self):
        r = self.post({**LOYAL, "frequency": 35.5})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.get_json()["fields"]["frequency"], "Must be a whole number.")

    def test_variety_cannot_exceed_orders(self):
        r = self.post({**LAPSED, "category_variety": 5})
        self.assertEqual(r.status_code, 422)
        self.assertIn("category_variety", r.get_json()["fields"])

    def test_avg_basket_must_match(self):
        r = self.post({**DEAL, "avg_basket": 900})
        self.assertEqual(r.status_code, 422)
        self.assertIn("450.00", r.get_json()["fields"]["avg_basket"])

    def test_body_not_json(self):
        r = self.client.post("/api/segment", data="hello", content_type="text/plain")
        self.assertEqual(r.status_code, 400)

    def test_json_but_not_object(self):
        r = self.post([1, 2, 3])
        self.assertEqual(r.status_code, 422)

    def test_cors_headers_present(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.headers["Access-Control-Allow-Origin"], "http://localhost:5173")
        pre = self.client.options("/api/segment")
        self.assertEqual(pre.status_code, 204)


if __name__ == "__main__":
    unittest.main()
