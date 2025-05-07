import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
import pickle
import datetime
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests

# Flask setup
app = Flask(__name__)
CORS(app)

# Dane OAuth i konfiguracja
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "https://calendar-service-pl5m.onrender.com/oauth2callback"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.pickle"
CALENDAR_ID = "be9b5f1bccf1c810003ce5bc5eb3493716031cf1ea5fdd9a9e52b4e6fe5b05e7@group.calendar.google.com"

# Obsługa autoryzacji OAuth
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
    with open(TOKEN_FILE, 'wb') as token:
        pickle.dump(flow.credentials, token)
    return "✅ Token zapisany. Możesz teraz korzystać z kalendarza."

# Pomocnicza funkcja do połączenia z Google Calendar
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

# Endpoint dostępnych dni
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
    free_days = []

    for day_offset in range((end - start).days + 1):
        day = start + datetime.timedelta(days=day_offset)
        day_start = day.isoformat() + 'Z'
        day_end = (day + datetime.timedelta(days=1)).isoformat() + 'Z'

        events = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=day_start,
            timeMax=day_end,
            singleEvents=True
        ).execute().get('items', [])

        if len(events) < 10:  # np. max 10 wizyt dziennie
            free_days.append(day.date().isoformat())

    return jsonify({"available_days": free_days})

# Endpoint dostępnych godzin
@app.route("/available-slots")
def available_slots():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Brak parametru 'date'"}), 400

    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Niepoprawny format daty (YYYY-MM-DD)"}), 400

    service = get_calendar_service()
    start = date.replace(hour=8)
    end = date.replace(hour=18)

    events = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start.isoformat() + 'Z',
        timeMax=end.isoformat() + 'Z',
        singleEvents=True
    ).execute().get('items', [])

    busy_ranges = [
        (datetime.datetime.fromisoformat(e['start']['dateTime'].replace('Z', '+00:00')),
         datetime.datetime.fromisoformat(e['end']['dateTime'].replace('Z', '+00:00')))
        for e in events
    ]

    free_slots = []
    slot_time = start
    while slot_time < end:
        slot_end = slot_time + datetime.timedelta(hours=1)
        if all(not (slot_time < b_end and slot_end > b_start) for b_start, b_end in busy_ranges):
            free_slots.append(f"{slot_time.strftime('%H:%M')}–{slot_end.strftime('%H:%M')}")
        slot_time += datetime.timedelta(hours=1)

    return jsonify({"free_slots": free_slots})

# Endpoint rezerwacji
@app.route("/book", methods=["POST"])
def book():
    data = request.json
    required = ["date", "slot", "name", "phone", "address", "problem", "urgency"]
    if not all(field in data for field in required):
        return jsonify({"error": "Brakuje wymaganych pól"}), 400

    try:
        start_hour, end_hour = data['slot'].split("–")
        start = datetime.datetime.strptime(f"{data['date']} {start_hour}", "%Y-%m-%d %H:%M")
        end = datetime.datetime.strptime(f"{data['date']} {end_hour}", "%Y-%m-%d %H:%M")
    except Exception:
        return jsonify({"error": "Niepoprawny format godziny"}), 400

    emoji_map = {"standard": "🟢", "urgent": "🟠", "now": "🔴"}
    emoji = emoji_map.get(data['urgency'], "🔵")

    summary = f"{emoji} {data['name']} – {data['problem']}"
    description = f"""
📞 Telefon: {data['phone']}
📍 Adres: {data['address']}
🛠️ Problem: {data['problem']}
⏱️ Typ wizyty: {emoji} ({data['urgency']})
"""

    service = get_calendar_service()
    event = {
        'summary': summary,
        'description': description.strip(),
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

# Root endpoint
@app.route("/")
def root():
    return "✅ Calendar service is running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
