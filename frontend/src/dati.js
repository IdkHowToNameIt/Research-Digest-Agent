/* ---------------------------------------------------------------------------
   Livello dati: lettura dei JSON prodotti dal backend e proiezione nel modello
   usato dalla UI. Nessun React qui dentro — sono funzioni pure, testabili da sole.

   I dati sono suddivisi per scalare: all'avvio si carica solo l'INDICE
   (data.json, leggero: per tema i soli gruppi recenti per la landing); il
   dettaglio di un tema (tema-<id>.json) arriva on-demand, e i corpi degli
   articoli per anno (tema-<id>-<anno>.json).
--------------------------------------------------------------------------- */

export const MESI = ['gen', 'feb', 'mar', 'apr', 'mag', 'giu',
  'lug', 'ago', 'set', 'ott', 'nov', 'dic']
export const MESI_FULL = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
  'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']
export const GIORNI_SETT = ['lun', 'mar', 'mer', 'gio', 'ven', 'sab', 'dom']

export const ETICHETTE_TEMA = {
  chip: 'Chip',
  data_center: 'Data center',
  energia: 'Energia',
  supply_chain: 'Supply chain',
  cloud_capacity: 'Cloud capacity',
}

// Set di pill del filtro periodo: la lista tema ragiona a giorni; la dashboard,
// a cadenza settimanale, aggiunge mesi/anno e "ultimo run".
export const RANGE_TEMA = [['all', 'Tutte'], ['7', '7 giorni'], ['30', '30 giorni'], ['90', '90 giorni']]
export const RANGE_DASH = [['all', 'Tutti'], ['30', '30 giorni'], ['90', '90 giorni'],
  ['365', '12 mesi'], ['run', 'Ultimo run']]

export const OPZIONI_PER_PAGINA = [10, 25, 50]

/* --------- date ------------------------------------------------------------ */

export function giorniFa(iso) {
  if (!iso) return 99999
  const d = new Date(iso + 'T00:00:00')
  if (isNaN(d.getTime())) return 99999
  const oggi = new Date()
  oggi.setHours(0, 0, 0, 0)
  return Math.round((oggi - d) / 86400000)
}

export function fmtData(iso) {
  const d = new Date((iso || '') + 'T00:00:00')
  if (isNaN(d.getTime())) return iso || ''
  return d.getDate() + ' ' + MESI[d.getMonth()] + ' ' + d.getFullYear()
}

/** Data compatta per i campi del filtro: "20 lug 26". Il trattino lungo è il
 *  segnaposto quando il campo è vuoto, non una stringa vuota. */
export function fmtDataBreve(iso) {
  const d = new Date((iso || '') + 'T00:00:00')
  if (isNaN(d.getTime())) return '—'
  return d.getDate() + ' ' + MESI[d.getMonth()] + ' ' + String(d.getFullYear()).slice(2)
}

export function pad2(n) { return String(n).padStart(2, '0') }

/* --------- numeri ---------------------------------------------------------- */

export function plurale(n, uno, molti) { return n === 1 ? uno : molti }
export function fmtNum(n) { return (n || 0).toLocaleString('it-IT') }

export function fmtEuro(n) {
  const v = n || 0
  // costi molto piccoli (free tier ~0): più decimali per non collassare a "€ 0,00"
  return '€ ' + v.toLocaleString('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: v > 0 && v < 0.01 ? 6 : 2,
  })
}

export function fmtLettura(min) { return min > 0 ? '~' + min + ' min di lettura' : '' }

export function nomeTema(id) { return ETICHETTE_TEMA[id] || id }

/* --------- proiezione degli articoli --------------------------------------- */

/** Proietta un articolo del JSON nel modello usato dalla UI. */
export function mapArt(a) {
  return {
    titolo: a.titolo,
    fonte: (a.fonti || []).map((f) => f.nome).join(' · '),
    fonti: a.fonti || [],
    data: a.data,
    sintesi: a.sintesi || '',
    perche: a.perche_conta || '',
    nota: a.note || null,
  }
}

/* --------- caricamento ----------------------------------------------------- */

/** Aggiunge ?v=<generato> a un file dati: cacheabile, si riscarica solo a run nuovo.
 *
 *  Serve ANCHE dopo il passaggio a Vite: gli asset dell'app hanno l'hash del
 *  contenuto nel nome, ma i JSON dei dati no — stesso nome a ogni run, contenuto
 *  diverso. Senza questo il browser servirebbe il digest della settimana prima.
 */
export function conVersione(file, generato) {
  return file + (generato ? '?v=' + encodeURIComponent(generato) : '')
}

/** Legge l'indice data.json e normalizza i temi. */
export async function caricaIndice(fetchImpl = fetch) {
  const resp = await fetchImpl('data.json', { cache: 'no-store' })
  if (!resp.ok) throw new Error('HTTP ' + resp.status)
  const dati = await resp.json()
  return {
    generato: dati.generato || '',
    sogliaNuovo: dati.badge_giorni != null ? dati.badge_giorni : 2,
    sogliaSettimana: dati.settimana_giorni != null ? dati.settimana_giorni : 7,
    // URL del Worker per l'invio email: presente solo se configurato nel backend.
    // Se vuoto, la scelta "ricevi via email" non viene offerta.
    invioEmailUrl: dati.invio_email_url || '',
    temi: (dati.temi || []).map((t) => ({
      id: t.id,
      nome: t.nome,
      file: t.file || 'tema-' + t.id + '.json',
      recenti: (t.recenti || []).map((r) => ({
        data: r.data,
        giorni: giorniFa(r.data),
        titolo: r.titolo || '',
        n: r.n_articoli || 0,
        minuti: r.minuti_lettura || 0,
      })),
    })),
  }
}

/** Lista leggera dei gruppi di un tema (metadati, niente corpi). */
export async function caricaTema(tema, generato, fetchImpl = fetch) {
  const resp = await fetchImpl(conVersione(tema.file, generato))
  if (!resp.ok) throw new Error('HTTP ' + resp.status)
  const dati = await resp.json()
  return (dati.gruppi || []).map((g) => ({
    data: g.data,
    giorni: giorniFa(g.data),
    titolo: g.titolo || '',
    n: g.n_articoli || 0,            // conteggio (dai metadati)
    minuti: g.minuti_lettura || 0,   // tempo di lettura stimato (dai metadati)
    anteprima: g.anteprima_titoli || [],
  }))
}

/** Corpi degli articoli di un anno per un tema: tema-<id>-<anno>.json. */
export async function caricaAnno(temaId, anno, generato, fetchImpl = fetch) {
  const file = 'tema-' + temaId + '-' + anno + '.json'
  const resp = await fetchImpl(conVersione(file, generato))
  if (!resp.ok) throw new Error('HTTP ' + resp.status)
  const dati = await resp.json()
  const perData = {}
  for (const g of dati.gruppi || []) {
    perData[g.data] = (g.articoli || []).map(mapArt)
  }
  return perData
}

/** Metriche di osservabilità: un record per run, prodotto dal backend.
 *
 *  Solo dati operativi — nessun contenuto editoriale, nessuna nota interna: il
 *  sito è pubblico (vedi DECISIONI §11). */
export async function caricaMetriche(fetchImpl = fetch) {
  const resp = await fetchImpl('metriche.json', { cache: 'no-store' })
  if (!resp.ok) throw new Error('HTTP ' + resp.status)
  const dati = await resp.json()
  return {
    generato: dati.generato || '',
    temi: dati.temi && dati.temi.length
      ? dati.temi
      : ['chip', 'data_center', 'energia', 'supply_chain', 'cloud_capacity'],
    // ogni run ottiene data (YYYY-MM-DD) e giorni-fa per il filtro periodo
    run: (dati.run || []).map((r) => {
      const data = (r.timestamp || '').slice(0, 10)
      return { ...r, data, giorni: giorniFa(data) }
    }),
  }
}

/* --------- filtro periodo (condiviso lista tema / dashboard) ---------------- */

/** True se il filtro periodo è attivo (pill diversa da "tutte" oppure date). */
export function filtroPeriodoAttivo(stato) {
  return (stato.val && stato.val !== 'all') || !!stato.dal || !!stato.al
}

/** Filtra per periodo elementi che espongono `data` (ISO) e `giorni`.
 *
 *  'run' è un caso a sé: tiene solo gli elementi della data più recente presente
 *  (l'ultimo run), non un intervallo. Negli altri casi pill e date Dal/Al si
 *  combinano in AND — restringono entrambe, nessuna prevale sull'altra.
 */
export function filtraPerPeriodo(items, stato) {
  if (stato.val === 'run') {
    const ultima = items.reduce((m, x) => (x.data && x.data > m ? x.data : m), '')
    return items.filter((x) => x.data === ultima)
  }
  const rg = stato.val && stato.val !== 'all' ? Number(stato.val) : null
  return items.filter((x) => {
    if (rg != null && x.giorni > rg) return false
    if (stato.dal && !(x.data && x.data >= stato.dal)) return false
    if (stato.al && !(x.data && x.data <= stato.al)) return false
    return true
  })
}
