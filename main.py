from flask import Flask, redirect, request, jsonify
import os
import pickle
import datetime
import google.auth.transport.requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from flask_cors import CORS

# 🔐 Pozwala testować OAuth przez HTTP (lokalnie lub w Render)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
CORS(app)

# Konfiguracja ogólna
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "dev-secret")

# Plik z tokenem autoryzacyjnym
TOKEN_FILE = "token.pickle"
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Dane OAuth z Google Cloud Console
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

@app.route("/free-slots", methods=["GET"])
def free_slots():
    try:
        if not os.path.exists(TOKEN_FILE):
            return jsonify({"error": "Brak tokena. Przejdź do /authorize"}), 401

        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

        if creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)

        service = build('calendar', 'v3', credentials=creds)

        now = datetime.datetime.utcnow()
        start = (now + datetime.timedelta(days=7)).isoformat() + 'Z'
        end = (now + datetime.timedelta(days=14)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        return jsonify({"events": events})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
