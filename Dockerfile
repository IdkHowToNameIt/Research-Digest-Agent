# Backend / generatore del Research Digest Agent (batch).
# Produce i file statici del sito (in /app/sito) e "invia" l'email.
# Usa Python 3.12 (wheel stabili; evita il problema pydantic cp314 di Python 3.14).
FROM python:3.12-slim

WORKDIR /app

# Dipendenze prima del codice, per sfruttare la cache dei layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Genera i dati del sito (data.json) e copia il frontend in /app/sito.
# Richiede GEMINI_API_KEY (per la sintesi): passarla come variabile d'ambiente.
CMD ["python", "main.py", "--config", "config.yaml"]
