from flask import Flask, redirect, request, jsonify
import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
import pickle
import datetime
import google.auth.transport.requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from flask_cors import CORS



app = Flask(__name__)
CORS(app)

TOKEN_FILE = "token.pickle"
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "https://calendar-service-pl5m.onrender.com/oauth2callback"

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

    with open(TOKEN_FILE, 'wb') as token:
        pickle.dump(creds, token)

    return "✅ Token zapisany. Możesz teraz korzystać z kalendarza."

def get_calendar_service():
    if not os.path.exists(TOKEN_FILE):
        raise Exception("Brak tokena. Przejdź do /authorize")

    with open(TOKEN_FILE, 'rb') as token:
        creds = pickle.load(token)

    if creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        with open(TOKEN_FILE, 'wb') as token:
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
        end = today + datetime.timedelta(days=7)
    elif urgency == "now":
        start = today
        end = today
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

    busy_days = set(event['start']['dateTime'][:10] for event in events if 'dateTime' in event['start'])

    all_days = [(start + datetime.timedelta(days=i)).date().isoformat() for i in range((end - start).days + 1)]
    available_days = [day for day in all_days if day not in busy_days]

    return jsonify({"available_days": available_days})

@app.route("/available-slots")
def available_slots():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Brak daty"}), 400

    date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    start = date.replace(hour=8)
    end = date.replace(hour=18)

    service = get_calendar_service()
    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start.isoformat() + 'Z',
        timeMax=end.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    busy_slots = [(datetime.datetime.fromisoformat(e['start']['dateTime']), datetime.datetime.fromisoformat(e['end']['dateTime'])) for e in events if 'dateTime' in e['start']]

    free_slots = []
    slot_start = start
    while slot_start + datetime.timedelta(hours=1) <= end:
        slot_end = slot_start + datetime.timedelta(hours=1)
        if not any(bs <= slot_start < be or bs < slot_end <= be for bs, be in busy_slots):
            free_slots.append(f"{slot_start.time().strftime('%H:%M')}–{slot_end.time().strftime('%H:%M')}")
        slot_start += datetime.timedelta(hours=1)

    return jsonify({"free_slots": free_slots})

@app.route("/book", methods=["POST"])
def book():
    data = request.get_json()
    date = data.get("date")
    slot = data.get("slot")
    name = data.get("name")
    phone = data.get("phone")
    address = data.get("address")
    problem = data.get("problem")
    urgency = data.get("urgency", "standard")

    if not all([date, slot, name, phone, address, problem]):
        return jsonify({"error": "Brakuje danych"}), 400

    emoji_map = {
        "standard": "🟢",
        "urgent": "🟠",
        "now": "🔴"
    }
    emoji = emoji_map.get(urgency, "🔵")

    summary = f"{emoji} {name} – {problem}"
    description = f"""
📞 Telefon: {phone}
📍 Adres: {address}
🛠️ Problem: {problem}
⏱️ Typ wizyty: {emoji} ({urgency})
"""

    date_obj = datetime.datetime.strptime(date, "%Y-%m-%d")
    start_hour, end_hour = slot.split("–")
    start_time = datetime.datetime.strptime(start_hour, "%H:%M").time()
    end_time = datetime.datetime.strptime(end_hour, "%H:%M").time()
    start = datetime.datetime.combine(date_obj, start_time)
    end = datetime.datetime.combine(date_obj, end_time)

    service = get_calendar_service()
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start.isoformat(),
            'timeZone': 'Europe/Warsaw',
        },
        'end': {
            'dateTime': end.isoformat(),
            'timeZone': 'Europe/Warsaw',
        },
    }
    created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()

    return jsonify({"status": "Zarezerwowano", "event_link": created_event.get("htmlLink")})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
