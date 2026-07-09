# Backend / generatore del Research Digest Agent (batch).
# Produce i file statici del sito (in /app/sito) e "invia" l'email.
# Usa Python 3.12 (wheel stabili; evita il problema pydantic cp314 di Python 3.14).
FROM python:3.12-slim

WORKDIR /app

# Dipendenze prima del codice, per sfruttare la cache dei layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: genera il sito in modalità demo offline (nessuna rete, nessuna API key).
# Per la modalità reale (Gemini): passare GEMINI_API_KEY e sovrascrivere il comando
#   con `python main.py --config config.yaml`.
CMD ["python", "main.py", "--demo", "--config", "config.demo.yaml"]
