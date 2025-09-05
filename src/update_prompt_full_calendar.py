import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import os

# --- Configurazioni ---
BASE_PROMPT_FILE = "base_prompt.json"   # Il tuo prompt di base con ruoli e regole
OUTPUT_PROMPT_FILE = "prompt.json"      # Il prompt aggiornato che Gemini userà
CALENDAR_URL = "https://www.e-labo.it/calendario-corsi/"

# --- Funzione per estrarre corsi dal calendario ---
def estrai_corsi_calendario():
    corsi = []
    try:
        r = requests.get(CALENDAR_URL)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Modifica il selettore secondo la struttura reale del calendario
        eventi = soup.select(".calendar-event")  # esempio: tutte le voci del calendario
        for evento in eventi:
            titolo = evento.select_one(".event-title").get_text(strip=True)
            data_testo = evento.select_one(".event-date").get_text(strip=True)
            
            # Prova a convertire la data in datetime
            try:
                data = datetime.strptime(data_testo, "%d/%m/%Y")
            except:
                data = None
            
            # Considera solo corsi futuri
            if data is None or data >= datetime.now():
                corsi.append(f"{titolo} ({data_testo})")
                
    except Exception as e:
        print("Errore nello scraping del calendario:", e)
    
    return corsi

# --- Carica il prompt base ---
with open(BASE_PROMPT_FILE, "r", encoding="utf-8") as f:
    base_prompt = json.load(f)

# --- Aggiungi informazioni aggiornate dal calendario ---
corsi = estrai_corsi_calendario()
info_sito = "\nInformazioni aggiornate dal calendario corsi E-labo:\n"
if corsi:
    info_sito += "Corsi programmati prossimamente:\n"
    for c in corsi:
        info_sito += f"- {c}\n"
else:
    info_sito += "Al momento non ci sono corsi programmati, ma possono essere attivati su richiesta.\n"

base_prompt["system_instruction"] += info_sito

# --- Salva il prompt aggiornato ---
with open(OUTPUT_PROMPT_FILE, "w", encoding="utf-8") as f:
    json.dump(base_prompt, f, ensure_ascii=False, indent=2)

print(f"✅ Prompt aggiornato salvato in {OUTPUT_PROMPT_FILE}")
