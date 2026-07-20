# Backend / generatore del Research Digest Agent (batch).
# Produce i file statici del sito (in /app/sito) e "invia" l'email.
# NB: si builda con contesto la root del repo (vedi docker-compose.yml), perché
# serve anche il frontend come template del sito.

# --- stadio 1: build del frontend -------------------------------------------
# Dal 2026-07-20 l'interfaccia è React+Vite e va COSTRUITA. La build sta qui e non
# fuori perché `frontend/dist/` è gitignored: da un clone pulito non esiste, e
# copiarla e basta avrebbe prodotto un sito senza interfaccia, in silenzio.
# Node 22: Vite 8 richiede ^20.19 || >=22.12.
FROM node:22-slim AS frontend

WORKDIR /frontend
# Prima il manifest, poi il codice: così `npm ci` si rifà solo se cambiano le
# dipendenze e non a ogni modifica di un componente.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- stadio 2: runtime Python ------------------------------------------------
# Usa Python 3.12 (wheel stabili; evita il problema pydantic cp314 di Python 3.14).
FROM python:3.12-slim

WORKDIR /app

# Dipendenze prima del codice, per sfruttare la cache dei layer.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .
# La build del frontend viene dallo stadio 1, non dal contesto: nel contesto
# `dist/` può mancare (gitignored) o essere vecchia.
COPY --from=frontend /frontend/dist ./frontend/dist

WORKDIR /app/backend

# Genera i dati del sito (data.json) e copia il frontend in /app/sito.
# Richiede GROQ_API_KEY (per la sintesi): passarla come variabile d'ambiente.
CMD ["python", "main.py", "--config", "config.yaml"]
