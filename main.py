
import os
import pickle
import base64
import datetime
import pytz
from datetime import datetime as dt, timedelta
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
CORS(app)

SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "https://calendar-service-pl5m.onrender.com/oauth2callback"
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

@app.route("/")
def index():
    return "✅ Calendar service is running"

@app.route("/authorize")
def authorize():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": [REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
    return redirect(auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": [REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    with open("token.pickle", "wb") as token:
        pickle.dump(creds, token)

    return "✅ Token zapisany. Możesz teraz korzystać z kalendarza."

def get_calendar_service():
    if os.getenv("GOOGLE_TOKEN_B64"):
        token_bytes = base64.b64decode(os.getenv("GOOGLE_TOKEN_B64"))
        creds = pickle.loads(token_bytes)
    elif os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    else:
        raise Exception("Brak tokena. Przejdź do /authorize")

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build('calendar', 'v3', credentials=creds)

@app.route("/available-days")
def available_days():
    urgency = request.args.get("urgency", "standard")
    today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if urgency == "standard":
        start = today + datetime.timedelta(days=7)
        end = today + datetime.timedelta(days=14)
    elif urgency == "urgent":
        start = today + datetime.timedelta(days=1)
        end = today + datetime.timedelta(days=6)
    elif urgency == "now":
        start = today
        end = today + datetime.timedelta(days=1)
    elif urgency == "plan":
        start = today + datetime.timedelta(days=15)
        end = today + datetime.timedelta(days=30)
    else:
        return jsonify({"error": "Nieznany parametr urgency"}), 400

    service = get_calendar_service()
    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start.isoformat() + 'Z',
        timeMax=end.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    booked_days = set()
    for event in events:
        date = event['start'].get('dateTime', event['start'].get('date'))[:10]
        booked_days.add(date)

    all_days = [(start + datetime.timedelta(days=i)).date().isoformat() for i in range((end - start).days + 1)]
    available_days = [day for day in all_days if day not in booked_days]

    return jsonify({"available_days": available_days})

LOG_FILE = "slots.log"

def log_to_file(message):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"[BŁĄD LOGOWANIA] {e}", flush=True)

@app.route("/available-slots")
def available_slots():
    date_str = request.args.get("date")
    duration_str = request.args.get("duration", "60")  # domyślnie 60 minut

    if not date_str:
        return jsonify({"error": "Brak daty"}), 400

    try:
        duration = int(duration_str)
        if duration not in [15, 30, 45, 60, 90, 120, 150, 180, 210, 240, 270, 300]:
            return jsonify({"error": "Nieprawidłowy czas trwania slotu"}), 400
    except ValueError:
        return jsonify({"error": "Błąd parsowania parametru duration"}), 400

    try:
        log_to_file(f"🔍 Żądanie slotów na dzień {date_str} z długością {duration} min")

        date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        warsaw = pytz.timezone("Europe/Warsaw")
        start_of_day = warsaw.localize(date.replace(hour=8, minute=0))
        end_of_day = warsaw.localize(date.replace(hour=18, minute=0))

        service = get_calendar_service()
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        log_to_file(f"📅 Liczba wydarzeń w kalendarzu: {len(events)}")

        busy_slots = []
        for event in events:
            start_dt = event['start'].get('dateTime')
            end_dt = event['end'].get('dateTime')
            if not start_dt or not end_dt:
                continue
            start = datetime.datetime.fromisoformat(start_dt)
            end = datetime.datetime.fromisoformat(end_dt)
            busy_slots.append((start, end))
            log_to_file(f"⛔ Zajęte: {start.strftime('%H:%M')}–{end.strftime('%H:%M')}")

        free_slots = []
        current = start_of_day
        while current + datetime.timedelta(minutes=duration) <= end_of_day:
            candidate_start = current
            candidate_end = current + datetime.timedelta(minutes=duration)

            overlaps = any(
                not (candidate_end <= busy_start or candidate_start >= busy_end)
                for (busy_start, busy_end) in busy_slots
            )

            label = f"{candidate_start.strftime('%H:%M')}–{candidate_end.strftime('%H:%M')}"
            if not overlaps:
                free_slots.append(label)
                log_to_file(f"✅ Dostępny slot: {label}")
            else:
                log_to_file(f"❌ Niedostępny slot (kolizja): {label}")

            current += datetime.timedelta(minutes=15)

        log_to_file(f"📦 Zwrócono {len(free_slots)} dostępnych slotów")
        return jsonify({"free_slots": free_slots})

    except Exception as e:
        log_to_file(f"💥 Błąd generowania slotów: {str(e)}")
        return jsonify({"error": f"Błąd generowania slotów: {str(e)}"}), 500


@app.route("/book", methods=["POST"])
def book():
    data = request.json
    date = data.get("date")
    slot = data.get("slot")
    name = data.get("name")
    phone = data.get("phone")
    address = data.get("address")
    problem = data.get("problem")
    urgency = data.get("urgency", "standard")
    override_now = data.get("override_now", False)

    if not all([date, slot, name, phone, address, problem]):
        return jsonify({"error": "Brak wymaganych danych"}), 400

    emoji = "NATYCHMIASTOWA"
    if override_now:
        emoji = "🔺"
    else:
        emojis = {
            "standard": "🟢", "standardowa": "🟢",
            "urgent": "🟠", "pilna": "🟠",
            "now": "🔴", "natychmiastowa": "🔴",
            "plan": "🔵", "planowa": "🔵"
         }
        emoji = emojis.get(urgency, "🟢")


    start_hour, end_hour = slot.split("–")
    start_datetime = datetime.datetime.strptime(f"{date} {start_hour}", "%Y-%m-%d %H:%M")
    end_datetime = datetime.datetime.strptime(f"{date} {end_hour}", "%Y-%m-%d %H:%M")

    event = {
        'summary': f"{emoji} {name} – {problem}",
        'location': address,
        'description': f"""
📞 Telefon: {phone}
📍 Adres: {address}
🛠️ Problem: {problem}
⏱️ Typ wizyty: {emoji} ({'NATYCHMIASTOWA (override)' if override_now else urgency.upper()})
""",
        'start': {
            'dateTime': start_datetime.isoformat(),
            'timeZone': 'Europe/Warsaw',
        },
        'end': {
            'dateTime': end_datetime.isoformat(),
            'timeZone': 'Europe/Warsaw',
        }
    }

    service = get_calendar_service()
    created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return jsonify({"status": "Zarezerwowano", "event_link": created_event.get("htmlLink")})

@app.route("/events-count")
def count_events():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Brak daty"}), 400

    try:
        service = get_calendar_service()
        start = dt.strptime(date_str, "%Y-%m-%d").replace(hour=8, minute=0).isoformat() + "Z"
        end = dt.strptime(date_str, "%Y-%m-%d").replace(hour=22, minute=0).isoformat() + "Z"

        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        return jsonify({"count": len(events)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
