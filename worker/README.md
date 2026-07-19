# DRA — Worker invio email (Fase 2 export PDF)

Relay che riceve dal sito `{ email, filename, pdf(base64), tema, data }` e inoltra il
PDF in allegato via **Resend** (HTTP API, niente SMTP). La API key di Resend vive
**solo** come secret del Worker: mai nel sito statico, mai nel repo.

```
Sito (pdf.js)  --POST-->  Cloudflare Worker (worker.js)  --HTTPS-->  Resend  --email-->  destinatario
```

## Cosa recuperare prima

- **Resend → API key**: dashboard Resend → *API Keys* → *Create API Key* (permesso
  *Sending access*). Copia la stringa `re_...` (mostrata una sola volta).
- **URL pubblico del sito**: serve come `ALLOWED_ORIGIN` (CORS), es.
  `https://utente.github.io` (senza slash finale).

> Senza un dominio verificato su Resend, l'invio funziona **solo verso la casella
> dell'account Resend**; gli altri destinatari ricevono un 403 (il Worker lo traduce
> in un messaggio chiaro). Per inviare a chiunque: Resend → *Domains* → verifica un
> dominio (gratis) e imposta `MITTENTE = "digest@tuodominio"`.

## Deploy A — dashboard Cloudflare (nessuna CLI)

1. Cloudflare → **Workers & Pages** → *Create* → *Create Worker* → dai un nome
   (es. `dra-mail`) → *Deploy* (crea lo scheletro).
2. *Edit code* → incolla **tutto** il contenuto di [`worker.js`](worker.js) → *Deploy*.
3. Worker → **Settings → Variables**:
   - *Add variable* → `ALLOWED_ORIGIN` = l'URL del tuo sito → *Save*.
   - (opzionale) *Add variable* → `MITTENTE` = `onboarding@resend.dev` (default se
     assente; cambialo solo con dominio verificato).
   - *Add variable* → `RESEND_API_KEY` = la key `re_...` → spunta **Encrypt** → *Save*.
     (È così che diventa un secret: non più leggibile dopo il salvataggio.)
4. Copia l'**URL del Worker** (in alto nella pagina del Worker, tipo
   `https://dra-mail.<tuo-sottodominio>.workers.dev`).

## Deploy B — Wrangler CLI (dal repo)

```bash
cd worker
wrangler login                       # OAuth nel browser, nessun token da copiare
# imposta ALLOWED_ORIGIN e MITTENTE in wrangler.toml, poi:
wrangler secret put RESEND_API_KEY   # incolla la key re_...
wrangler deploy                      # stampa l'URL del Worker
```

## Collegare il sito

Metti l'URL del Worker nella config del backend, poi rigenera il sito:

- `backend/config.yaml` → `sito.invio_email_url: "https://dra-mail.<...>.workers.dev"`
- oppure variabile d'ambiente `INVIO_EMAIL_URL` (ha la precedenza; su GitHub Actions:
  *Settings → Secrets and variables → Actions → Variables*).

Se `invio_email_url` è vuoto, il sito mostra solo **Scarica PDF**; appena è valorizzato
compare anche **Invia via email**.

## Prova veloce

```bash
curl -X POST "$WORKER_URL" -H "Content-Type: application/json" \
  -d '{"email":"LA-TUA-CASELLA-RESEND","pdf":"'"$(printf '%%PDF-1.4 test' | base64 -w0)"'","filename":"test.pdf","tema":"Chip","data":"2026-07-17"}'
# atteso: {"ok":true,"id":"..."}  (verso la tua casella Resend)
```
