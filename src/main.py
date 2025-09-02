from appwrite.client import Client
from appwrite.exception import AppwriteException
import os
import json
import google.generativeai as genai

cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, x-appwrite-key",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Credentials": "true"
}

def main(context):
    try:
        context.log("🚀 Funzione avviata.")

        client = (
            Client()
            .set_endpoint(os.environ["APPWRITE_FUNCTION_API_ENDPOINT"])
            .set_project(os.environ["APPWRITE_FUNCTION_PROJECT_ID"])
            .set_key(os.environ["APPWRITE_FUNCTION_API_KEY"])
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
                raw_body = context.req.body or "{}"
                data = raw_body if isinstance(raw_body, dict) else json.loads(raw_body)

                user_msg = data.get("msg", "").strip()
                history = data.get("history", [])

                context.log(f"📝 Messaggio utente: {user_msg}")

                prompt_path = os.path.join(os.path.dirname(__file__), "prompt.json")
                if not os.path.exists(prompt_path):
                    raise FileNotFoundError("prompt.json non trovato nella funzione.")

                with open(prompt_path, "r") as f:
                    prompt_data = json.load(f)

                system_instruction = prompt_data.get("system_instruction", "")
                prompt_parts = [{"text": system_instruction + "\n"}]
                for m in history[-10:]:
                    prompt_parts.append({"text": f"Utente: {m.get('message', '')}\n"})
                prompt_parts.append({"text": f"Utente: {user_msg}\n"})

                gemini_api_key = os.environ.get("GEMINI_API_KEY")
                if not gemini_api_key:
                    raise EnvironmentError("Variabile GEMINI_API_KEY non impostata.")

                genai.configure(api_key=gemini_api_key)
                model = genai.GenerativeModel("gemini-2.0-flash-thinking-exp-01-21")
                response = model.generate_content(
                    prompt_parts,
                    generation_config={
                        "temperature": 0.7,
                        "max_output_tokens": 2048,
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
                context.error(f"❌ Errore nella generazione: {e}")
                return {
                    "statusCode": 500,
                    "headers": cors_headers,
                    "body": json.dumps({"error": str(e)})
                }

        return {
            "statusCode": 405,
            "headers": cors_headers,
            "body": json.dumps({"error": "Metodo non supportato"})
        }

    except Exception as e:
        context.error(f"💥 Errore globale: {e}")
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": str(e)})
        }
