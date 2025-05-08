from flask import Flask, redirect, request, jsonify
import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
import base64
import pickle
import datetime
import google.auth.transport.requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from flask_cors import CORS

# Inicjalizacja aplikacji
app = Flask(__name__)
CORS(app)

# Ustawienia środowiskowe
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "https://calendar-service-pl5m.onrender.com/oauth2callback"
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Pozwolenie na HTTP (dla Render w wersji dev)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Główna strona serwisu
@app.route("/")
def index():
    return "✅ Calendar service is running"

# Autoryzacja Google OAuth2
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

# Callback po autoryzacji – zapis tokena jako base64
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

    with open("token.pickle", "wb") as token_file:
        pickle.dump(creds, token_file)

    return "✅ Token zapisany. Pobierz go przez /download-token i dodaj do Render jako GOOGLE_TOKEN_B64."

# Tymczasowy endpoint do pobrania tokena w Base64
@app.route("/download-token")
def download_token():
    with open("token.pickle", "rb") as f:
        token_bytes = f.read()
        token_b64 = base64.b64encode(token_bytes).decode("utf-8")
    return jsonify({"token_b64": token_b64})

# Funkcja do pobrania połączenia z Google Calendar z ENV
def get_calendar_service():
    token_b64 = os.getenv("GOOGLE_TOKEN_B64")
    if not token_b64:
        raise Exception("Brak tokena. Przejdź do /authorize i ustaw GOOGLE_TOKEN_B64 w Render")

    token_bytes = base64.b64decode(token_b64.encode("utf-8"))
    creds = pickle.loads(token_bytes)

    if creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        # UWAGA: nie zapisujemy zaktualizowanego tokena – jeśli chcesz, zaktualizuj GOOGLE_TOKEN_B64 ręcznie

    return build('calendar', 'v3', credentials=creds)

# Endpoint testowy do pobrania wydarzeń między 7. a 14. dniem
@app.route("/free-slots", methods=["GET"])
def free_slots():
    try:
        service = get_calendar_service()

        now = datetime.datetime.utcnow()
        start = (now + datetime.timedelta(days=7)).isoformat() + 'Z'
        end = (now + datetime.timedelta(days=14)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='be9b5f1bccf1c810003ce5bc5eb3493716031cf1ea5fdd9a9e52b4e6fe5b05e7@group.calendar.google.com',
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
