from appwrite.client import Client
from appwrite.exception import AppwriteException
import os
import json
import csv
from datetime import datetime
import google.generativeai as genai

# Headers CORS
cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, x-appwrite-key",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Credentials": "true"
}

# --- import necessari (aggiungili in cima a main.py) ---
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- funzione per leggere eventi oggi dal calendario office ---
def get_today_events_from_google(credentials_info, calendar_id, tz_name="Europe/Rome"):
    creds = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=["https://www.googleapis.com/auth/calendar.readonly"]
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=start,
        timeMax=end,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    return events_result.get("items", [])


# --- funzione di normalizzazione (semplice, estendibile) ---
def normalize_event_presence(event):
    summary = (event.get("summary") or "").lower()
    location = (event.get("location") or "").lower()
    desc = (event.get("description") or "").lower()

    # regole semplici — adatta ai tuoi casi
    if any(k in summary for k in ["sopralluogo","cantiere","cliente","visit"]):
        return "Fuori sede"
    if any(k in summary for k in ["smart","remoto","da casa","smart working"]):
        return "Smart working"
    if "ufficio" in summary or "sede" in summary or "arzignano" in location:
        return "In ufficio"
    return "Occupato"


# --- funzione per mappare presenza per lista di nomi ---
def map_staff_presence(events, staff_names):
    # inizializziamo tutti come "Libero"
    presences = {name: "Libero" for name in staff_names}

    for ev in events:
        text_blob = " ".join([
            ev.get("summary","") or "",
            ev.get("description","") or "",
            ev.get("location","") or ""
        ]).lower()

        for name in staff_names:
            if name.lower() in text_blob:
                presences[name] = normalize_event_presence(ev)

        # prova anche dagli attendees (se presenti)
        for a in ev.get("attendees", []) or []:
            a_text = ((a.get("displayName","") or "") + " " + (a.get("email","") or "")).lower()
            for name in staff_names:
                if name.lower() in a_text:
                    presences[name] = normalize_event_presence(ev)

    return presences

def load_courses_from_csv(file_path):
    """Legge i corsi dal CSV ufficiale e li converte in testo leggibile per il prompt."""
    courses = []
    try:
        with open(file_path, newline='', encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                titolo = row.get("Title", "").strip()
                start_date = row.get("Start Date", "").strip()
                city = row.get("City", "").strip()

                if titolo and start_date:
                    try:
                        # Se la data è nel formato "YYYY-MM-DD HH:MM:SS"
                        dt = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
                        data_fmt = dt.strftime("%d/%m/%Y %H:%M")
                    except Exception:
                        data_fmt = start_date  # se non riesce, la lascia così com’è

                    courses.append(f"- {titolo} il {data_fmt} a {city}")
    except Exception as e:
        courses.append(f"[⚠️ Errore nel caricamento corsi: {e}]")

    return "\n".join(courses)


def main(context):
    # Inizializza Appwrite Client
    client = (
        Client()
        .set_endpoint(os.environ["APPWRITE_FUNCTION_API_ENDPOINT"])
        .set_project(os.environ["APPWRITE_FUNCTION_PROJECT_ID"])
        .set_key(context.req.headers.get("x-appwrite-key", ""))
    )

    context.log("✅ Connessione Appwrite OK.")

    if context.req.method == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": cors_headers,
            "body": ""
        }

    if context.req.path == "/ping":
        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": "Pong"
        }

    if context.req.method == "POST":
        try:
            # ✅ Gestione sicura del body
            raw_body = context.req.body
            if not raw_body:
                data = {}
            elif isinstance(raw_body, dict):
                data = raw_body
            else:
                try:
                    data = json.loads(raw_body)
                except Exception:
                    context.error(f"❌ Body non è JSON valido: {raw_body}")
                    data = {}

            user_msg = data.get("msg", "").strip()
            history = data.get("history", [])

            if not user_msg:
                return {
                    "statusCode": 400,
                    "headers": cors_headers,
                    "body": json.dumps({"error": "Campo 'msg' mancante o vuoto"})
                }
# leggi le credenziali JSON dall'environment (Appwrite)
creds_json = os.environ.get("GOOGLE_CREDENTIALS")
calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
tz = os.environ.get("GOOGLE_CALENDAR_TZ", "Europe/Rome")
staff_json = os.environ.get("STAFF_NAMES", "[]")

try:
    credentials_info = json.loads(creds_json) if creds_json else None
except Exception:
    credentials_info = None

staff_names = json.loads(staff_json) if staff_json else []

events = []
if credentials_info and calendar_id:
    try:
        events = get_today_events_from_google(credentials_info, calendar_id, tz)
    except Exception as e:
        context.error(f"Errore lettura Google Calendar: {e}")

# otteniamo mappa nome->stato
presence_map = map_staff_presence(events, staff_names)

# poi metti presence_map in system_instruction (es. elenco testuale)
presence_lines = []
for name, state in presence_map.items():
    presence_lines.append(f"- {name} → {state}")

system_instruction += "\n\n📌 Presenze oggi:\n" + ("\n".join(presence_lines) if presence_lines else "Nessuna informazione sulle presenze oggi.")

            # Carica prompt.json
            with open(os.path.join(os.path.dirname(__file__), "prompt.json"), "r", encoding="utf-8") as f:
                prompt_data = json.load(f)

            system_instruction = prompt_data.get("system_instruction", "")

            # 🔽 Data odierna
            today = datetime.today().strftime("%d/%m/%Y")

            # 🔽 Carica corsi dal CSV (stesso repo della funzione)
            courses_file = os.path.join(os.path.dirname(__file__), "Corsi E_Labo.csv")
            courses_text = load_courses_from_csv(courses_file)

            # Aggiorna il system instruction con data odierna e corsi
            system_instruction += (
                f"\n\n📅 Oggi è il {today}. "
                f"Quando rispondi, considera questa data come riferimento.\n\n"
                f"📌 Calendario corsi aggiornato:\n{courses_text}"
            )

            # Costruzione del prompt
            sorted_messages = history[-10:]  # Ultimi 10 messaggi
            prompt_parts = [{"text": system_instruction + "\n"}]

            for m in sorted_messages:
                prompt_parts.append({"text": f"Utente: {m.get('message', '')}\n"})

            prompt_parts.append({"text": f"Utente: {user_msg}\n"})

            # Configura Gemini
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel("gemini-2.0-flash-thinking-exp-01-21")

            # Chiamata a Gemini
            response = model.generate_content(
                prompt_parts,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 4096,
                    "top_k": 64,
                    "top_p": 0.95
                }
            )

            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps({"reply": response.text})
            }

        except Exception as e:
            context.error(f"❌ Errore durante la generazione: {e}")
            return {
                "statusCode": 500,
                "headers": cors_headers,
                "body": json.dumps({"error": str(e)})
            }

    return {
        "statusCode": 200,
        "headers": cors_headers,
        "body": json.dumps({
            "info": "Usa POST con {'msg': '...'} e 'history': [...] per parlare con Gemini."
        })
    }
