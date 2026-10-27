"""Flask API for the Customer Segmentation project.

Run from the project root:
    python backend/app.py
The API starts on http://localhost:5000

Endpoints
    GET  /api/health    -> is the API up and is the model loaded?
    GET  /api/segments  -> all segment profiles (name, description, action, size, medians) + valid input ranges
    POST /api/segment   -> JSON with one customer's 7 features -> their segment and how they compare to it

The pipeline (log + scaler + k-means) is trained in notebook/Customer_Segmentation.ipynb and loaded ONCE when the
server starts. We never retrain on a request.
"""
import json
import math
import os

import joblib
import pandas as pd
from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "models", "segmentation_pipeline.joblib")
PROFILES_PATH = os.path.join(BASE_DIR, "models", "segment_profiles.json")

# Which website may call this API from a browser (the Vite dev server by default).
ALLOWED_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

# A customer whose closest centre is almost as far as the second-closest one is "borderline".
BORDERLINE_RATIO = 0.8

app = Flask(__name__)

# ---- load the model and the profiles once at start-up ----
if not os.path.exists(MODEL_PATH) or not os.path.exists(PROFILES_PATH):
    raise SystemExit("Model files not found. Run notebook/Customer_Segmentation.ipynb first to create models/.")
pipeline = joblib.load(MODEL_PATH)
with open(PROFILES_PATH, encoding="utf-8") as f:
    profiles = json.load(f)

FEATURES = profiles["features"]
INTEGER_FIELDS = set(profiles["integer_features"])
RANGES = profiles["valid_ranges"]
SEGMENTS = {s["id"]: s for s in profiles["segments"]}

# Short human-readable labels used in the comparison text.
LABELS = {
    "recency_days": "days since last order",
    "frequency": "orders per year",
    "monetary": "total spend (₹)",
    "avg_basket": "average basket (₹)",
    "coupon_rate": "coupon rate",
    "app_share": "app share",
    "category_variety": "categories bought",
}


@app.after_request
def add_cors_headers(response):
    """Allow the React app (a different port = a different 'origin') to call this API."""
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def validate(payload):
    """Return (clean_row, errors). errors is a dict: field -> message a person can understand."""
    errors, row = {}, {}
    if not isinstance(payload, dict):
        return None, {"body": "Send a JSON object with the customer's feature values."}

    for field in FEATURES:
        low, high = RANGES[field]
        value = payload.get(field)
        if value is None or value == "":
            errors[field] = "This field is required."
            continue
        if isinstance(value, bool):                      # true/false is not a number here
            errors[field] = "Must be a number."
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            errors[field] = "Must be a number."
            continue
        if math.isnan(number) or math.isinf(number):
            errors[field] = "Must be a real number."
        elif field in INTEGER_FIELDS and not number.is_integer():
            errors[field] = "Must be a whole number."
        elif not (low <= number <= high):
            errors[field] = f"Must be between {low:g} and {high:g}."
        else:
            row[field] = number

    # Rules that involve two fields (only checked when the single fields are fine).
    if "frequency" in row and "category_variety" in row and row["category_variety"] > row["frequency"]:
        errors["category_variety"] = "Cannot be more than the number of orders (each order has one main category)."
    if "frequency" in row and "monetary" in row and "avg_basket" in row:
        expected = row["monetary"] / row["frequency"]
        if abs(row["avg_basket"] - expected) > max(1.0, 0.01 * expected):
            errors["avg_basket"] = f"Should equal total spend / orders = {expected:.2f}."
    return row, errors


def compare_to_segment(row, segment):
    """For every feature say whether this customer is above, below or close to the segment median."""
    comparison = []
    for field in FEATURES:
        median = segment["medians"][field]
        value = row[field]
        # "close" = within 10% of the median (or within 0.05 for rates, which are between 0 and 1)
        tolerance = 0.05 if field in ("coupon_rate", "app_share") else max(abs(median) * 0.10, 0.5)
        if abs(value - median) <= tolerance:
            position = "close"
        elif value > median:
            position = "above"
        else:
            position = "below"
        comparison.append({"feature": field, "label": LABELS[field], "value": value,
                           "segment_median": median, "position": position})
    return comparison


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "model": profiles["model"], "segments": len(SEGMENTS)})


@app.get("/api/segments")
def segments():
    return jsonify({
        "model": profiles["model"],
        "customers_clustered": profiles["customers_clustered"],
        "silhouette": profiles["silhouette"],
        "features": FEATURES,
        "valid_ranges": RANGES,
        "overall_medians": profiles["overall_medians"],
        "segments": profiles["segments"],
    })


@app.route("/api/segment", methods=["POST", "OPTIONS"])
def assign_segment():
    if request.method == "OPTIONS":           # browser "preflight" check before a POST
        return ("", 204)
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Request body must be JSON (Content-Type: application/json)."}), 400

    row, errors = validate(payload)
    if errors:
        return jsonify({"error": "Some inputs are invalid.", "fields": errors}), 422

    features = pd.DataFrame([row], columns=FEATURES)
    segment_id = int(pipeline.predict(features)[0])
    distances = sorted(pipeline.transform(features)[0])      # distance to every segment centre, smallest first
    ratio = distances[0] / distances[1] if distances[1] > 0 else 0.0
    segment = SEGMENTS[segment_id]
    return jsonify({
        "segment_id": segment_id,
        "segment_name": segment["name"],
        "description": segment["description"],
        "suggested_action": segment["suggested_action"],
        "fit": "borderline" if ratio > BORDERLINE_RATIO else "clear",
        "distance_ratio": round(float(ratio), 3),
        "comparison": compare_to_segment(row, segment),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
