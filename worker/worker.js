/* ===========================================================================
   DRA — Worker di invio email (Fase 2 export PDF).
   Riceve dal sito statico { email, filename, pdf(base64), tema, data }, e inoltra
   il PDF in allegato via Resend (HTTP API, niente SMTP). La API key vive SOLO qui,
   come secret del Worker (env.RESEND_API_KEY) — mai nel sito.

   Variabili d'ambiente (impostate nella dashboard Cloudflare):
     RESEND_API_KEY   (secret)  la chiave re_... di Resend
     ALLOWED_ORIGIN   (var)     origine del sito ammessa in CORS, es.
                                "https://utente.github.io" (senza slash finale).
                                Se assente, si accettano tutte le origini ('*').
     MITTENTE         (var, opz.) indirizzo "from". Senza dominio verificato su
                                Resend DEVE restare "onboarding@resend.dev" (default).

   Anti-abuso (demo): metodo limitato a POST, origine bloccata via CORS, tetto di
   dimensione sul PDF, validazione dell'email. Un rate-limit robusto richiede un
   binding KV/Durable Object: qui si tiene volutamente essenziale.
=========================================================================== */

const MAX_PDF_BYTES = 5 * 1024 * 1024;         // 5 MB sul PDF decodificato
const RESEND_ENDPOINT = "https://api.resend.com/emails";

export default {
  async fetch(request, env) {
    const origin = env.ALLOWED_ORIGIN || "*";
    const cors = {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
    };

    // preflight CORS
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }
    if (request.method !== "POST") {
      return json({ ok: false, errore: "Metodo non consentito." }, 405, cors);
    }
    if (!env.RESEND_API_KEY) {
      return json({ ok: false, errore: "Servizio email non configurato." }, 500, cors);
    }

    // corpo della richiesta
    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, errore: "Richiesta non valida." }, 400, cors);
    }

    const email = String(body.email || "").trim();
    const pdf = String(body.pdf || "");           // base64 puro (senza prefisso data:)
    const filename = sanitizeNome(body.filename) || "digest.pdf";
    const tema = String(body.tema || "").slice(0, 80);
    const data = String(body.data || "").slice(0, 20);

    if (!emailValida(email)) {
      return json({ ok: false, errore: "Indirizzo email non valido." }, 400, cors);
    }
    if (!pdf) {
      return json({ ok: false, errore: "PDF mancante." }, 400, cors);
    }
    // dimensione approssimata del decodificato: base64 ~ 4/3 dei byte reali
    if (pdf.length * 0.75 > MAX_PDF_BYTES) {
      return json({ ok: false, errore: "PDF troppo grande." }, 413, cors);
    }

    const mittente = env.MITTENTE || "onboarding@resend.dev";
    const oggetto = tema ? `Digest DRA — ${tema}${data ? " · " + data : ""}` : "Digest DRA";
    const corpoHtml =
      `<p>In allegato il digest richiesto dal sito DRA` +
      `${tema ? ` (<strong>${escapeHtml(tema)}</strong>${data ? " · " + escapeHtml(data) : ""})` : ""}.</p>` +
      `<p style="color:#888;font-size:12px">Inviato automaticamente da DRA — kakashi.ventures.</p>`;

    // inoltro a Resend
    let resp;
    try {
      resp = await fetch(RESEND_ENDPOINT, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: `DRA <${mittente}>`,
          to: [email],
          subject: oggetto,
          html: corpoHtml,
          attachments: [{ filename, content: pdf }],
        }),
      });
    } catch (e) {
      return json({ ok: false, errore: "Rete verso il servizio email non raggiungibile." }, 502, cors);
    }

    if (!resp.ok) {
      // Resend in test mode (senza dominio verificato) rifiuta i destinatari
      // diversi dalla casella dell'account con un 403: messaggio chiaro per la demo.
      let dettaglio = "";
      try { dettaglio = (await resp.json())?.message || ""; } catch {}
      if (resp.status === 403) {
        return json({
          ok: false,
          errore: "In modalità demo (senza dominio verificato) l'invio è abilitato solo verso la casella dell'account Resend.",
          dettaglio,
        }, 403, cors);
      }
      return json({ ok: false, errore: "Invio non riuscito.", dettaglio }, 502, cors);
    }

    let id = "";
    try { id = (await resp.json())?.id || ""; } catch {}
    return json({ ok: true, id }, 200, cors);
  },
};

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors },
  });
}

function emailValida(s) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s) && s.length <= 254;
}

function sanitizeNome(s) {
  return String(s || "").replace(/[^a-zA-Z0-9._-]+/g, "-").slice(0, 100);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
