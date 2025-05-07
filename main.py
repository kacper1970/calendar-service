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

# Token i OAuth
TOKEN_FILE = "token.pickle"
SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "https://calendar-service-pl5m.onrender.com/oauth2callback"
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID")

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
    available = []
    for i in range((end - start).days):
        day = start + datetime.timedelta(days=i)
        date_str = day.date().isoformat()
        if date_str not in busy_days:
            available.append(date_str)

    return jsonify({"available_days": available})

@app.route("/available-slots")
def available_slots():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Brak parametru 'date'"}), 400

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

    busy_slots = [(datetime.datetime.fromisoformat(e['start']['dateTime']),
                   datetime.datetime.fromisoformat(e['end']['dateTime'])) for e in events if 'dateTime' in e['start']]

    slots = []
    current = start
    while current + datetime.timedelta(hours=1) <= end:
        slot_start = current
        slot_end = current + datetime.timedelta(hours=1)
        conflict = any(bs < slot_end and be > slot_start for bs, be in busy_slots)
        if not conflict:
            slots.append(f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}")
        current += datetime.timedelta(minutes=60)

    return jsonify({"available_slots": slots})

@app.route("/book", methods=["POST"])
def book():
    data = request.json
    date = data.get("date")
    time = data.get("time")
    summary = data.get("summary", "Wizyta klienta")

    if not date or not time:
        return jsonify({"error": "Brakuje daty lub godziny"}), 400

    start_time = datetime.datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    end_time = start_time + datetime.timedelta(hours=1)

    service = get_calendar_service()
    event = {
        'summary': summary,
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Europe/Warsaw'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Europe/Warsaw'}
    }

    created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return jsonify({"status": "zarezerwowano", "event_id": created_event['id']})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
