> Nota: questo è un esempio dimostrativo, prodotto dalla modalità demo su un feed
> finto. Gli URL `example.com` non sono fonti reali, quindi questo digest non
> soddisfa il criterio sulle fonti: serve solo a mostrare la forma del risultato.

# Research Digest — Ecosistema agenti e MCP

_Esempio generato in modalità demo_

## 1. Rilasciata la versione 1.29 dell'SDK MCP per TypeScript

- **Fonte:** Feed finto di esempio (KVA)
- **Link:** https://example.com/news/mcp-sdk-ts-1-29
- **Data:** 15 giugno 2026
- **Tag:** mcp, sdk

La nuova versione dell'SDK introduce un transport compatibile con gli standard del web, pensato per l'esecuzione su runtime "edge". In pratica rende più semplice pubblicare un server MCP su piattaforme come Cloudflare Workers.

**Perché conta:** è esattamente lo stack che consigliamo per la Track A; un deploy più semplice significa meno tempo perso sull'infrastruttura.

## 2. OpenAI Agents SDK aggiunge timeout e guardrail per gli strumenti

- **Fonte:** Feed finto di esempio (KVA)
- **Link:** https://example.com/news/agents-sdk-timeout
- **Data:** 17 giugno 2026
- **Tag:** agenti, affidabilità

Ora si può imporre un tempo massimo a ogni strumento e decidere cosa fare in caso di errore. Sono due controlli che spostano un agente dal "funziona una volta" al "gira da solo senza sorvegliarlo".

**Perché conta:** tocca direttamente i criteri di affidabilità della Track B (gestione errori e tempi sotto controllo).

## 3. Guida: pubblicare un MCP server su Cloudflare Workers

- **Fonte:** Feed finto di esempio (KVA)
- **Link:** https://example.com/blog/mcp-su-workers
- **Data:** 18 giugno 2026
- **Tag:** mcp, deploy

Un tutorial che parte dal codice e arriva a un indirizzo pubblico, passo dopo passo, usando il transport via web.

**Perché conta:** è il punto in cui i gruppi della Track A si bloccano più spesso; una guida lineare riduce il rischio prima della giornata finale.

## 4. Pattern: agenti affidabili con output strutturato

- **Fonte:** Feed finto di esempio (KVA)
- **Link:** https://example.com/blog/agenti-output-strutturato
- **Data:** 19 giugno 2026
- **Tag:** agenti, schemi

Definire la forma dell'output (con Pydantic o Zod) è il primo passo per un agente che non inventa: il modello è costretto a riempire campi precisi invece di scrivere testo libero.

**Perché conta:** è uno dei criteri di valutazione, e spiega perché lo schema viene prima del modello.
