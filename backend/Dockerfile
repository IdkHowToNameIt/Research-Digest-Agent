# Backend / generatore del Research Digest Agent (batch).
# Produce i file statici del sito (in /app/sito) e "invia" l'email.
# Usa Python 3.12 (wheel stabili; evita il problema pydantic cp314 di Python 3.14).
# NB: si builda con contesto la root del repo (vedi docker-compose.yml), perché
# serve anche frontend/concept/index.html come template del sito.
FROM python:3.12-slim

WORKDIR /app

# Dipendenze prima del codice, per sfruttare la cache dei layer.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .
WORKDIR /app/backend

# Genera i dati del sito (data.json) e copia il frontend in /app/sito.
# Richiede GROQ_API_KEY (per la sintesi): passarla come variabile d'ambiente.
CMD ["python", "main.py", "--config", "config.yaml"]
