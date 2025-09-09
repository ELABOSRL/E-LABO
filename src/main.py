from appwrite.client import Client
from appwrite.exception import AppwriteException
import os
import json
import csv
import google.generativeai as genai

# Headers CORS
cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, x-appwrite-key",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Credentials": "true"
}


def load_courses_from_csv(file_path):
    """Legge i corsi dal CSV e li converte in testo leggibile per il prompt."""
    courses = []
    try:
        with open(file_path, newline='', encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                titolo = row.get("Titolo", "").strip()
                data = row.get("Data", "").strip()
                orario = row.get("Orario", "").strip()
                link = row.get("Link", "").strip()
                if titolo:
                    courses.append(f"- {titolo} ({data}, {orario}) → {link}")
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

            # Carica prompt.json
            with open(os.path.join(os.path.dirname(__file__), "prompt.json"), "r", encoding="utf-8") as f:
                prompt_data = json.load(f)

            system_instruction = prompt_data.get("system_instruction", "")

            # Carica corsi dal CSV (stesso repo di main.py)
            courses_file = os.path.join(os.path.dirname(__file__), "Corsi E_Labo.csv")
            courses_text = load_courses_from_csv(courses_file)

            # Aggiorna il system instruction con i corsi
            system_instruction += "\n\n📅 Calendario corsi aggiornato:\n" + courses_text

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
