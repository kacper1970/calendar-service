# main.py
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# Fake storage of booked appointments (to be replaced by database later)
BOOKED = set()

@app.route("/")
def index():
    return "✅ Calendar service is running"

@app.route("/available", methods=["GET"])
def available():
    try:
        start_str = request.args.get("start")
        end_str = request.args.get("end")

        if not start_str or not end_str:
            return jsonify({"error": "Missing start or end date"}), 400

        start = datetime.strptime(start_str, "%Y-%m-%d").date()
        end = datetime.strptime(end_str, "%Y-%m-%d").date()

        available_slots = []
        current = start
        while current <= end:
            if current.strftime("%Y-%m-%d") not in BOOKED:
                available_slots.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        return jsonify({"available": available_slots})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/book", methods=["POST"])
def book():
    try:
        data = request.get_json()
        date = data.get("date")  # format YYYY-MM-DD

        if not date:
            return jsonify({"error": "Missing date"}), 400

        if date in BOOKED:
            return jsonify({"status": "unavailable", "message": "Date already booked"}), 409

        BOOKED.add(date)
        return jsonify({"status": "booked", "date": date}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
