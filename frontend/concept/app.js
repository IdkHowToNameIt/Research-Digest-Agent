/* ---------------------------------------------------------------------------
   App del sito interno: legge i dati REALI da data.json (prodotto dal backend)
   e genera lato client le pagine — homepage, cronologia per tema, articolo.
   Le date degli articoli sono assolute (YYYY-MM-DD): da esse si derivano la
   soglia "Nuovo aggiornamento" (badge_giorni) e la vista "questa settimana"
   (settimana_giorni), entrambe lette da data.json.
--------------------------------------------------------------------------- */
let TEMI = [];
let GENERATO = '';        // data del run (token per il cache-busting dei file tema)
let SOGLIA_NUOVO = 2;      // giorni: badge "Nuovo aggiornamento" (sovrascritto da data.json)
let SOGLIA_SETTIMANA = 7;  // giorni: rientra nel digest "di questa settimana"
let TEMA_CORRENTE = null;    // id del tema nella vista lista-gruppi (per i filtri data)
let GRUPPO_CORRENTE = null;  // {id, data} nella vista dettaglio (per il filtro fonte)
let FILTRO_DATE = {dal:'', al:''};      // intervallo "Dal-Al" selezionato col calendario custom
let CAL = {campo:null, anno:0, mese:0}; // stato del popup calendario (quale campo, mese visualizzato)
let PAGINA = 1;                          // pagina corrente nella lista-gruppi di un tema
let PER_PAGINA = 10;                     // gruppi per pagina (default); scelta persistente tra i temi
const OPZIONI_PER_PAGINA = [10, 25, 50]; // scelte del selettore "Per pagina"
const MESI = ["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"];
const MESI_FULL = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
  "luglio","agosto","settembre","ottobre","novembre","dicembre"];
const GIORNI_SETT = ["lun","mar","mer","gio","ven","sab","dom"];

// Il filtro periodo (pill + calendario) è condiviso tra la lista di un tema e la
// dashboard: una sola vista è montata per volta, quindi basta indirizzare la sua
// callback di aggiornamento alla vista corrente.
let FILTRO_ONCHANGE = null;
let DASH = null;                         // dati dashboard (metriche.json), on-demand
const ETICHETTE_TEMA = {chip:'Chip', data_center:'Data center', energia:'Energia',
  supply_chain:'Supply chain', cloud_capacity:'Cloud capacity'};
// Set di pill del filtro periodo: la lista tema ragiona a giorni; la dashboard, a
// cadenza settimanale, aggiunge mesi/anno e "ultimo run".
const RANGE_TEMA = [['all','Tutte'],['7','7 giorni'],['30','30 giorni'],['90','90 giorni']];
const RANGE_DASH = [['all','Tutti'],['30','30 giorni'],['90','90 giorni'],['365','12 mesi'],['run','Ultimo run']];

function giorniFa(iso){
  if(!iso) return 99999;
  const d = new Date(iso + "T00:00:00");
  if(isNaN(d.getTime())) return 99999;
  const oggi = new Date(); oggi.setHours(0,0,0,0);
  return Math.round((oggi - d) / 86400000);
}
function fmtData(iso){
  const d = new Date((iso||"") + "T00:00:00");
  if(isNaN(d.getTime())) return iso || "";
  return d.getDate()+" "+MESI[d.getMonth()]+" "+d.getFullYear();
}
function trovaTema(id){ return TEMI.find(t=>t.id===id); }

const app = document.getElementById('app');

/* proietta un articolo del JSON nel modello usato dalla UI */
function mapArt(a){
  return {
    titolo: a.titolo,
    fonte: (a.fonti||[]).map(function(f){return f.nome;}).join(' · '),
    fonti: a.fonti||[],
    data: a.data,
    sintesi: a.sintesi||'',
    perche: a.perche_conta||'',
    nota: a.note||null
  };
}

/* --------- caricamento dei dati reali -----------------------------------------
   I dati sono suddivisi per scalare: all'avvio si carica solo l'INDICE (data.json,
   leggero: per tema i soli gruppi recenti per la landing); il dettaglio completo
   di un tema (tema-<id>.json) è caricato on-demand da caricaTema() aprendo il tema. */
async function caricaDati(){
  try{
    const resp = await fetch('data.json', {cache:'no-store'});
    if(!resp.ok) throw new Error('HTTP '+resp.status);
    const dati = await resp.json();
    if(dati.badge_giorni != null) SOGLIA_NUOVO = dati.badge_giorni;
    if(dati.settimana_giorni != null) SOGLIA_SETTIMANA = dati.settimana_giorni;
    GENERATO = dati.generato || '';
    TEMI = (dati.temi||[]).map(function(t){
      return {
        id: t.id, nome: t.nome,
        file: t.file || ('tema-'+t.id+'.json'),
        // gruppi recenti (solo data/titolo/conteggio) per i box della landing
        recenti: (t.recenti||[]).map(function(r){
          return {data: r.data, giorni: giorniFa(r.data), titolo: r.titolo||'', n: r.n_articoli||0};
        }),
        gruppi: null   // dettaglio completo: caricato on-demand (caricaTema)
      };
    });
    vaiHome();
  }catch(err){
    app.innerHTML = '<section class="view home"><div class="hero">'
      + '<div class="kicker">Digest settimanale interno</div>'
      + '<h1 class="title">Digest Research Agent</h1>'
      + '<p class="sub">Dati non ancora disponibili ('+err.message+'). '
      + 'Il digest viene rigenerato ogni settimana.</p></div></section>';
  }
}

/* aggiunge ?v=<generato> a un file dati: cacheabile, si riscarica solo a run nuovo */
function conVersione(file){
  return file + (GENERATO ? ('?v=' + encodeURIComponent(GENERATO)) : '');
}

/* carica (una volta) la LISTA LEGGERA di un tema: tema-<id>.json (solo metadati
   dei gruppi, niente corpi). Basta a lista + filtri; i corpi arrivano per anno. */
async function caricaTema(t){
  if(t.gruppi) return t.gruppi;   // già in cache di sessione
  const resp = await fetch(conVersione(t.file));
  if(!resp.ok) throw new Error('HTTP '+resp.status);
  const dett = await resp.json();
  t.gruppi = (dett.gruppi||[]).map(function(g){
    return {
      data: g.data,
      giorni: giorniFa(g.data),
      titolo: g.titolo||'',
      n: g.n_articoli||0,             // conteggio (dai metadati)
      anteprima: g.anteprima_titoli||[],
      articoli: null                  // corpi caricati per anno on-demand (caricaDettaglioGiorno)
    };
  });
  return t.gruppi;
}

/* carica i CORPI degli articoli del giorno `g`, prendendo il bucket annuale
   tema-<id>-<anno>.json (un solo fetch per anno, riusato per gli altri giorni
   dello stesso anno). Popola g.articoli e lo mette in cache sul tema. */
async function caricaDettaglioGiorno(t, g){
  if(g.articoli) return g.articoli;              // giorno già caricato
  const anno = (g.data || '').slice(0, 4);
  if(!t.dettaglio) t.dettaglio = {};             // mappa data -> articoli
  if(!t.anni) t.anni = {};                       // anni già scaricati
  if(!t.anni[anno]){
    const resp = await fetch(conVersione('tema-' + t.id + '-' + anno + '.json'));
    if(!resp.ok) throw new Error('HTTP '+resp.status);
    const bucket = await resp.json();
    (bucket.gruppi||[]).forEach(function(gr){
      t.dettaglio[gr.data] = (gr.articoli||[]).map(mapArt);
    });
    t.anni[anno] = true;
  }
  g.articoli = t.dettaglio[g.data] || [];
  return g.articoli;
}

/* --- icone tema: una per tema, stesso stile (stroke lineare), stesso peso --- */
const ICONE_TEMA = {
  chip: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><line x1="9" y1="2" x2="9" y2="7"/><line x1="15" y1="2" x2="15" y2="7"/><line x1="9" y1="17" x2="9" y2="22"/><line x1="15" y1="17" x2="15" y2="22"/><line x1="2" y1="9" x2="7" y2="9"/><line x1="2" y1="15" x2="7" y2="15"/><line x1="17" y1="9" x2="22" y2="9"/><line x1="17" y1="15" x2="22" y2="15"/>',
  data_center: '<rect x="4" y="3" width="16" height="8" rx="1.5"/><rect x="4" y="13" width="16" height="8" rx="1.5"/><circle cx="8" cy="7" r="1" fill="currentColor" stroke="none"/><circle cx="8" cy="17" r="1" fill="currentColor" stroke="none"/>',
  energia: '<polygon points="13,2 4,14 11,14 9,22 18,10 11,10"/>',
  supply_chain: '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><line x1="8.6" y1="7.6" x2="10" y2="15.5"/><line x1="15.4" y1="7.6" x2="14" y2="15.5"/><line x1="9" y1="6" x2="15" y2="6"/>',
  cloud_capacity: '<path d="M7 18a4.5 4.5 0 0 1-1-8.9A5 5 0 0 1 16 8a3.8 3.8 0 0 1 1 7.5" /><path d="M7 18h9.5"/>'
};
function iconaTema(id, dim){
  const s = dim||18;
  return `<svg class="tema-svg" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONE_TEMA[id]||''}</svg>`;
}

function iconaOsserva(dim){
  const s = dim||18;
  return `<svg class="tema-svg" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 17a8 8 0 0 1 16 0"/><line x1="12" y1="17" x2="16.5" y2="11.5"/><circle cx="12" cy="17" r="1.3" fill="currentColor" stroke="none"/></svg>`;
}

function plurale(n, uno, molti){ return n===1 ? uno : molti; }
function pad2(n){ return String(n).padStart(2,'0'); }
function fmtNum(n){ return (n||0).toLocaleString('it-IT'); }
function fmtEuro(n){
  const v = n||0;
  // costi molto piccoli (free tier ~0): mostra più decimali per non collassare a 0,00
  return '€ ' + v.toLocaleString('it-IT', {minimumFractionDigits:2, maximumFractionDigits: v>0 && v<0.01 ? 6 : 2});
}
function nomeTema(id){
  const t = trovaTema(id);
  return (t && t.nome) || ETICHETTE_TEMA[id] || id;
}

/* una notizia nella colonna di lettura del digest: numero d'ordine, titolo,
   fonte (link), tag del tema, sintesi completa, eventuale nota, "perché conta". */
function voceReport(tema, a, n){
  const fonti = (a.fonti||[]).map(f =>
    f.link ? `<a href="${f.link}" target="_blank" rel="noopener">${f.nome} ↗</a>` : f.nome
  ).join(' · ') || a.fonte;
  return `<article class="art" id="art-${n}">
      <div class="art-head"><span class="art-n">${pad2(n)}</span><h4>${a.titolo}</h4></div>
      <div class="meta"><span class="fonte">${fonti}</span>
        <span class="tag">${iconaTema(tema.id,13)}${tema.nome}</span> · ${fmtData(a.data)}</div>
      ${a.nota?`<div class="nota">${a.nota}</div>`:''}
      <p class="sintesi">${a.sintesi}</p>
      <div class="perche"><strong>Perché conta:</strong> ${a.perche}</div>
    </article>`;
}

/* ---------------------------- HOMEPAGE ----------------------------
   Un box per OGNI tema. Se il tema ha novità nella settimana mostra il gruppo più
   recente (titolo riassuntivo + data); altrimenti resta comunque presente con lo
   stato "Nessun aggiornamento settimanale". Il click porta alla lista del tema. */
function boxTema(t){
  // usa i gruppi recenti dell'indice (t.recenti), non il dettaglio (non ancora caricato)
  const recenti = t.recenti.filter(g => g.giorni <= SOGLIA_SETTIMANA);
  if(!recenti.length){
    // nessuna novità nella settimana: box presente ma in stato "vuoto" (storico apribile)
    return `<div class="box box-vuota reveal" data-tilt onclick="vaiTema('${t.id}')">
      <h3><span class="tema-ic">${iconaTema(t.id,22)}</span>${t.nome}</h3>
      <div class="box-vuoto">Nessun aggiornamento settimanale</div>
      <span class="apri">Apri ${t.nome} →</span>
    </div>`;
  }
  const g0 = recenti[0];                                   // più recente (backend ordina desc)
  const nuovo = g0.giorni <= SOGLIA_NUOVO;
  const nNews = recenti.reduce((s,g)=>s+g.n, 0);
  return `<div class="box reveal" data-tilt onclick="vaiTema('${t.id}')">
      <h3><span class="tema-ic">${iconaTema(t.id,22)}</span>${t.nome}</h3>
      <div class="box-data">${fmtData(g0.data)} ${nuovo?'<span class="badge-nuovo">Nuovo</span>':''}</div>
      <div class="box-titolo">${g0.titolo}</div>
      <div class="box-conta">${nNews} ${plurale(nNews,'aggiornamento','aggiornamenti')} questa settimana</div>
      <span class="apri">Apri ${t.nome} →</span>
    </div>`;
}

function vaiHome(){
  const oggi = fmtData(new Date().toISOString().slice(0,10));

  const nav = TEMI.map(t =>
    `<button class="pill" onclick="vaiTema('${t.id}')">${iconaTema(t.id,15)}${t.nome}</button>`
  ).join('')
  + `<button class="pill pill-osserva" onclick="vaiDashboard()">${iconaOsserva(15)}Osservabilità</button>`;

  // un box per ogni tema: quelli senza novità restano visibili con stato "vuoto"
  const boxes = TEMI.map(boxTema).join('');

  app.innerHTML = `<section class="view home">
    <div class="hero">
      <div class="kicker">Digest settimanale interno</div>
      <h1 class="title">Digest Research Agent</h1>
      <p class="sub">Infrastruttura &amp; Hardware AI — chip, data center, energia, supply chain, capacità cloud.</p>
      <div class="settimana">Settimana del ${oggi}</div>
    </div>
    <div class="temi-nav">${nav}</div>
    <main>
      <div class="sez-titolo">Aggiornamenti di questa settimana</div>
      <div class="sez-nota">Un box per ogni tema: le notizie dello stesso giorno sono un unico digest.</div>
      <div class="boxes">${boxes}</div>
    </main>
  </section>`;
  attivaEffetti();
}

/* ------------------- LISTA GRUPPI DI UN TEMA ---------------------
   Un gruppo per giorno, rappresentato dal titolo riassuntivo; il click apre il
   dettaglio. In cima, filtri per DATA (periodo rapido + intervallo dal/al). */
function cardGruppo(id, g){
  const nuovo = g.giorni <= SOGLIA_NUOVO;
  const n = g.n;                                  // conteggio dai metadati (corpi non caricati)
  const preview = n>1
    ? `<ul class="preview">${g.anteprima.slice(0,3).map(tit=>`<li>${tit}</li>`).join('')}
         ${n>3?`<li class="piu">…e altre ${n-3}</li>`:''}</ul>` : '';
  return `<div class="gruppo-card reveal" onclick="vaiGruppo('${id}','${g.data}')">
      <div class="meta">${fmtData(g.data)} ${nuovo?'<span class="badge-nuovo">Nuovo</span>':''}
        · ${n} ${plurale(n,'aggiornamento','aggiornamenti')}</div>
      <h4>${g.titolo}</h4>
      ${preview}
      <span class="apri">Apri il digest del giorno →</span>
    </div>`;
}

/* ---- filtro periodo riusabile (lista tema + dashboard) ------------------
   Stato letto dai controlli (pill attiva + intervallo dal/al) e applicato in modo
   PURO a una lista di item con {data:'YYYY-MM-DD', giorni:int}: così la stessa
   logica serve la lista dei gruppi e i pannelli della dashboard, senza duplicarla. */
function statoFiltroPeriodo(){
  const pill = document.querySelector('.filtro-range .pill-f.attivo');
  return {val: pill ? pill.dataset.giorni : 'all', dal: FILTRO_DATE.dal, al: FILTRO_DATE.al};
}

function filtraPerPeriodo(items, st){
  if(st.val === 'run'){                       // solo gli item del run/giorno più recente
    const ultima = items.reduce((m,x)=> (x.data && x.data > m) ? x.data : m, '');
    return items.filter(x => x.data === ultima);
  }
  const rg = (st.val && st.val !== 'all') ? Number(st.val) : null;
  return items.filter(x=>{
    if(rg != null && x.giorni > rg) return false;
    if(st.dal && !(x.data && x.data >= st.dal)) return false;
    if(st.al && !(x.data && x.data <= st.al)) return false;
    return true;
  });
}

function filtroPeriodoAttivo(st){ return (st.val && st.val !== 'all') || !!st.dal || !!st.al; }

function controlliFiltroData(range){
  const rng = range || RANGE_TEMA;
  const pills = rng.map((r,i)=>
    `<button class="pill-f${i===0?' attivo':''}" data-giorni="${r[0]}" onclick="attivaRange(this)">${r[1]}</button>`
  ).join('');
  return `<div class="filtri">
      <div class="filtro-range">${pills}</div>
      <div class="filtro-date">
        <span class="filtro-lbl">Periodo</span>
        <div class="date-range">
          <button class="date-field" id="campo-dal" onclick="apriCalendario('dal',event)">
            <span class="df-lbl">Dal</span><span class="df-val" id="val-dal">—</span></button>
          <span class="range-sep">→</span>
          <button class="date-field" id="campo-al" onclick="apriCalendario('al',event)">
            <span class="df-lbl">Al</span><span class="df-val" id="val-al">—</span></button>
          <div id="calendario" class="cal-pop" hidden onclick="event.stopPropagation()"></div>
        </div>
        <button class="btn-azzera nascosto" onclick="azzeraFiltriData()">✕ Azzera</button>
      </div>
    </div>`;
}

function attivaRange(el){
  el.parentElement.querySelectorAll('.pill-f').forEach(p=>p.classList.remove('attivo'));
  el.classList.add('attivo');
  PAGINA = 1;               // un nuovo filtro riparte dalla prima pagina
  if(FILTRO_ONCHANGE) FILTRO_ONCHANGE();
}

function azzeraFiltriData(){
  FILTRO_DATE = {dal:'', al:''};
  PAGINA = 1;
  aggiornaCampiData();
  chiudiCalendario();
  document.querySelectorAll('.filtro-range .pill-f').forEach(p=>
    p.classList.toggle('attivo', p.dataset.giorni === 'all'));   // torna alla prima pill
  if(FILTRO_ONCHANGE) FILTRO_ONCHANGE();
}

/* ---- date picker custom (calendario) del filtro "Periodo" -------------- */
function fmtDataBreve(iso){
  const d = new Date((iso||'') + "T00:00:00");
  if(isNaN(d.getTime())) return '—';
  return d.getDate() + " " + MESI[d.getMonth()] + " " + String(d.getFullYear()).slice(2);
}

function aggiornaCampiData(){
  const vd = document.getElementById('val-dal'), va = document.getElementById('val-al');
  if(vd) vd.textContent = FILTRO_DATE.dal ? fmtDataBreve(FILTRO_DATE.dal) : '—';
  if(va) va.textContent = FILTRO_DATE.al ? fmtDataBreve(FILTRO_DATE.al) : '—';
  const cd = document.getElementById('campo-dal'), ca = document.getElementById('campo-al');
  if(cd) cd.classList.toggle('valorizzato', !!FILTRO_DATE.dal);
  if(ca) ca.classList.toggle('valorizzato', !!FILTRO_DATE.al);
}

function apriCalendario(campo, ev){
  if(ev) ev.stopPropagation();
  CAL.campo = campo;
  const base = FILTRO_DATE[campo] ? new Date(FILTRO_DATE[campo] + "T00:00:00") : new Date();
  CAL.anno = base.getFullYear();
  CAL.mese = base.getMonth();
  renderCalendario();
  const pop = document.getElementById('calendario');
  if(pop) pop.hidden = false;
}

function calNav(delta){
  CAL.mese += delta;
  if(CAL.mese < 0){ CAL.mese = 11; CAL.anno--; }
  if(CAL.mese > 11){ CAL.mese = 0; CAL.anno++; }
  renderCalendario();
}

function renderCalendario(){
  const pop = document.getElementById('calendario');
  if(!pop) return;
  const {anno, mese, campo} = CAL;
  const offset = (new Date(anno, mese, 1).getDay() + 6) % 7;   // lun=0
  const giorniMese = new Date(anno, mese + 1, 0).getDate();
  const dal = FILTRO_DATE.dal, al = FILTRO_DATE.al;
  const oggiIso = new Date().toISOString().slice(0,10);
  let celle = '';
  for(let i=0; i<offset; i++) celle += '<span class="cal-vuoto"></span>';
  for(let g=1; g<=giorniMese; g++){
    const iso = `${anno}-${String(mese+1).padStart(2,'0')}-${String(g).padStart(2,'0')}`;
    const cls = ['cal-g'];
    // disabilita i giorni che creerebbero un intervallo invertito (Al<Dal o Dal>Al)
    const off = (campo === 'al'  && dal && iso < dal) ||
                (campo === 'dal' && al  && iso > al);
    if(off) cls.push('off');
    if(iso === dal || iso === al) cls.push('sel');            // estremi selezionati
    else if(dal && al && iso > dal && iso < al) cls.push('in-range'); // giorni intermedi
    if(iso === oggiIso) cls.push('oggi');
    const attr = off ? 'disabled' : `onclick="calSeleziona('${iso}',event)"`;
    celle += `<button class="${cls.join(' ')}" ${attr}>${g}</button>`;
  }
  pop.innerHTML = `
    <div class="cal-head">
      <button class="cal-nav" onclick="calNav(-1)" aria-label="Mese precedente">‹</button>
      <span class="cal-titolo">${MESI_FULL[mese]} ${anno}</span>
      <button class="cal-nav" onclick="calNav(1)" aria-label="Mese successivo">›</button>
    </div>
    <div class="cal-sett">${GIORNI_SETT.map(d=>`<span>${d}</span>`).join('')}</div>
    <div class="cal-griglia">${celle}</div>`;
}

function calSeleziona(iso, ev){
  if(ev) ev.stopPropagation();
  // ignora le selezioni che invertirebbero l'intervallo (i giorni sono già disabilitati)
  if((CAL.campo === 'al'  && FILTRO_DATE.dal && iso < FILTRO_DATE.dal) ||
     (CAL.campo === 'dal' && FILTRO_DATE.al  && iso > FILTRO_DATE.al)) return;
  FILTRO_DATE[CAL.campo] = iso;
  PAGINA = 1;
  aggiornaCampiData();
  chiudiCalendario();
  if(FILTRO_ONCHANGE) FILTRO_ONCHANGE();
}

function chiudiCalendario(){
  const pop = document.getElementById('calendario');
  if(pop) pop.hidden = true;
  CAL.campo = null;
}

// chiusura del calendario al click fuori / con Esc (registrata una sola volta)
document.addEventListener('click', function(e){
  const pop = document.getElementById('calendario');
  if(!pop || pop.hidden) return;
  if(e.target.closest('#calendario') || e.target.closest('.date-field')) return;
  chiudiCalendario();
});
document.addEventListener('keydown', function(e){ if(e.key === 'Escape') chiudiCalendario(); });

function renderListaGruppi(){
  const t = trovaTema(TEMA_CORRENTE);
  const cont = document.getElementById('lista-gruppi');
  if(!t || !cont) return;
  const st = statoFiltroPeriodo();
  let gruppi = filtraPerPeriodo(t.gruppi, st);
  // paginazione: mostra solo PER_PAGINA gruppi per volta (evita scroll infiniti).
  // La pagina corrente resta nei limiti disponibili (i filtri possono ridurre i risultati).
  const totale = gruppi.length;
  const totPagine = Math.max(1, Math.ceil(totale / PER_PAGINA));
  PAGINA = Math.min(Math.max(PAGINA, 1), totPagine);
  const inizio = (PAGINA - 1) * PER_PAGINA;
  const pagina = gruppi.slice(inizio, inizio + PER_PAGINA);

  cont.innerHTML = totale
    ? pagina.map(g=>cardGruppo(t.id, g)).join('')
      + controlliPaginazione(totale, totPagine, inizio, pagina.length)
    : '<p class="sez-nota">Nessun aggiornamento per il periodo selezionato.</p>';
  // il tasto Azzera compare solo quando c'è un filtro attivo
  const btn = document.querySelector('.btn-azzera');
  if(btn) btn.classList.toggle('nascosto', !filtroPeriodoAttivo(st));
  attivaEffetti();
}

/* barra di paginazione della lista-gruppi: selettore "Per pagina" (10/25/50,
   default 10) + navigazione Prec/Succ. La nav compare solo se i risultati
   superano una pagina; il selettore c'è sempre (quando ci sono risultati). */
function controlliPaginazione(totale, totPagine, inizio, mostrati){
  const opzioni = OPZIONI_PER_PAGINA.map(n=>
    `<option value="${n}"${n===PER_PAGINA?' selected':''}>${n}</option>`
  ).join('');
  const da = totale ? inizio + 1 : 0;
  const a = inizio + mostrati;
  const nav = totPagine > 1
    ? `<div class="pag-nav">
         <button class="pag-btn" ${PAGINA<=1?'disabled':''} onclick="vaiPagina(-1)">‹ Prec</button>
         <span class="pag-stato">Pagina ${PAGINA} di ${totPagine}</span>
         <button class="pag-btn" ${PAGINA>=totPagine?'disabled':''} onclick="vaiPagina(1)">Succ ›</button>
       </div>`
    : '';
  return `<div class="paginazione">
      <div class="pag-info">
        <label class="pag-perpag">Per pagina
          <select onchange="cambiaPerPagina(this)">${opzioni}</select>
        </label>
        <span class="pag-conta">${da}–${a} di ${totale}</span>
      </div>
      ${nav}
    </div>`;
}

function cambiaPerPagina(sel){
  PER_PAGINA = Number(sel.value) || 10;
  PAGINA = 1;                 // cambiando la dimensione si riparte dalla prima pagina
  renderListaGruppi();
}

function vaiPagina(delta){
  PAGINA += delta;
  renderListaGruppi();
  // riporta in cima alla lista, per non ritrovarsi a metà della pagina successiva
  const main = document.querySelector('.crono');
  if(main) main.scrollIntoView({behavior:'smooth', block:'start'});
}

async function vaiTema(id){
  const t = trovaTema(id);
  if(!t) return;
  TEMA_CORRENTE = id;
  FILTRO_DATE = {dal:'', al:''};   // i filtri data non persistono tra temi diversi
  FILTRO_ONCHANGE = renderListaGruppi;  // il filtro periodo aggiorna la lista del tema
  PAGINA = 1;                      // ogni tema riparte dalla prima pagina
  // subito la testata + un segnaposto di caricamento (il dettaglio arriva via fetch)
  app.innerHTML = `<section class="view"><main class="crono">
      <button class="indietro" onclick="vaiHome()">← Home</button>
      <h2><span class="tema-ic">${iconaTema(t.id,26)}</span>${t.nome}</h2>
      <div id="tema-corpo"><p class="sez-nota">Caricamento…</p></div>
    </main></section>`;
  window.scrollTo({top:0,behavior:'smooth'});
  try{
    await caricaTema(t);
  }catch(err){
    if(TEMA_CORRENTE !== id) return;                 // l'utente ha già navigato altrove
    const corpo = document.getElementById('tema-corpo');
    if(corpo) corpo.innerHTML = '<p class="sez-nota">Dettaglio del tema non disponibile ('+err.message+').</p>';
    return;
  }
  if(TEMA_CORRENTE !== id) return;                    // navigazione cambiata durante il fetch
  const corpo = document.getElementById('tema-corpo');
  if(!corpo) return;
  corpo.innerHTML = `${t.gruppi.length ? controlliFiltroData()
        : '<p class="sez-nota">Nessun articolo in archivio per questo tema.</p>'}
      <div id="lista-gruppi"></div>`;
  renderListaGruppi();
}

/* ---------------- DETTAGLIO DEL GRUPPO (giorno) ------------------
   Le notizie di quel tema in quel giorno, suddivise per intero. Se le notizie
   provengono da PIÙ fonti, in cima compare un filtro per fonte. */
function controlliFiltroFonte(fonti){
  const chips = ['(tutte)'].concat(fonti).map((f,i)=>
    `<button class="chip-f${i===0?' attivo':''}" data-fonte="${i===0?'':f.replace(/"/g,'&quot;')}"
        onclick="attivaFonte(this)">${f}</button>`
  ).join('');
  return `<div class="filtro-fonte"><span class="filtro-lbl">Fonte:</span>${chips}</div>`;
}

function attivaFonte(el){
  el.parentElement.querySelectorAll('.chip-f').forEach(c=>c.classList.remove('attivo'));
  el.classList.add('attivo');
  renderArticoliGruppo();
}

function gruppoCorrente(){
  if(!GRUPPO_CORRENTE) return null;
  const t = trovaTema(GRUPPO_CORRENTE.id);
  return t ? {t, g: t.gruppi.find(x=>x.data===GRUPPO_CORRENTE.data)} : null;
}

function scrollAVoce(el){
  const t = document.getElementById(el.dataset.target);
  if(t) t.scrollIntoView({behavior:'smooth', block:'start'});
}

/* evidenzia nell'indice la voce correntemente in lettura, mentre si scorre */
function attivaIndice(){
  const links = [...document.querySelectorAll('.idx-lista a[data-target]')];
  if(!links.length) return;
  const map = new Map(links.map(l=>[l.dataset.target, l]));
  const io = new IntersectionObserver(entries=>{
    entries.forEach(e=>{
      if(e.isIntersecting){
        links.forEach(l=>l.classList.remove('attivo'));
        const l = map.get(e.target.id);
        if(l) l.classList.add('attivo');
      }
    });
  }, {rootMargin:'-15% 0px -75% 0px'});
  document.querySelectorAll('.digest-lettura .art').forEach(a=>io.observe(a));
}

function renderArticoliGruppo(){
  const cur = gruppoCorrente();
  const lettura = document.getElementById('digest-lettura');
  const indice = document.getElementById('digest-indice');
  if(!cur || !cur.g || !lettura) return;
  const sel = document.querySelector('.filtro-fonte .chip-f.attivo');
  const fonte = sel ? sel.dataset.fonte : '';
  const articoli = fonte ? cur.g.articoli.filter(a=>a.fonte===fonte) : cur.g.articoli;

  lettura.innerHTML = articoli.length
    ? articoli.map((a,i)=>voceReport(cur.t, a, i+1)).join('')
    : '<p class="sez-nota">Nessuna notizia per la fonte selezionata.</p>';

  if(indice){
    // l'indice serve solo con più di una notizia
    indice.innerHTML = articoli.length > 1
      ? `<div class="idx-tit">Nella giornata</div>
         <ol class="idx-lista">${articoli.map((a,i)=>
           `<li><a data-target="art-${i+1}" onclick="scrollAVoce(this)">
              <span class="idx-n">${pad2(i+1)}</span><span>${a.titolo}</span></a></li>`).join('')}</ol>`
      : '';
  }
  attivaIndice();
}

async function vaiGruppo(id, data){
  const t = trovaTema(id);
  if(!t || !t.gruppi) return vaiTema(id);
  const g = t.gruppi.find(x=>x.data===data);
  if(!g) return vaiTema(id);
  GRUPPO_CORRENTE = {id, data};
  const nuovo = g.giorni <= SOGLIA_NUOVO;
  // testata subito (dai metadati) + segnaposto: i corpi arrivano dal bucket annuale
  app.innerHTML = `<section class="view"><main class="crono report">
      <button class="indietro" onclick="vaiTema('${id}')">← ${t.nome}</button>
      <div class="giorno-testata">
        <h2>${g.titolo}</h2>
        <div class="giorno-sub"><span class="tag">${iconaTema(t.id,13)}${t.nome}</span>
          · ${fmtData(g.data)} ${nuovo?'<span class="badge-nuovo">Nuovo</span>':''}
          · ${g.n} ${plurale(g.n,'aggiornamento','aggiornamenti')}</div>
      </div>
      <div id="gruppo-corpo"><p class="sez-nota">Caricamento…</p></div>
    </main></section>`;
  window.scrollTo({top:0,behavior:'smooth'});
  try{
    await caricaDettaglioGiorno(t, g);
  }catch(err){
    if(!GRUPPO_CORRENTE || GRUPPO_CORRENTE.data !== data) return;
    const corpo = document.getElementById('gruppo-corpo');
    if(corpo) corpo.innerHTML = '<p class="sez-nota">Dettaglio del giorno non disponibile ('+err.message+').</p>';
    return;
  }
  if(!GRUPPO_CORRENTE || GRUPPO_CORRENTE.data !== data) return;   // navigazione cambiata
  const corpo = document.getElementById('gruppo-corpo');
  if(!corpo) return;
  const fonti = [...new Set(g.articoli.map(a=>a.fonte).filter(Boolean))];
  const filtro = fonti.length > 1 ? controlliFiltroFonte(fonti) : '';
  corpo.innerHTML = `${filtro}
      <div class="digest-layout">
        <aside id="digest-indice" class="digest-indice"></aside>
        <div id="digest-lettura" class="digest-lettura"></div>
      </div>`;
  renderArticoliGruppo();
}

/* ===================== DASHBOARD DI OSSERVABILITÀ =======================
   Legge metriche.json (un record per run, prodotto dal backend) e mostra, per il
   periodo scelto col filtro riusato dalla lista tema: stato delle fonti, costi,
   deduplica e copertura dei 5 sotto-temi. Nessun dato editoriale né nota interna:
   solo metriche operative. Il sito è pubblico (vedi DECISIONI): sul free tier i
   costi sono ~0; in produzione gira in intranet. */
async function caricaDashboard(){
  if(DASH) return DASH;
  const resp = await fetch('metriche.json', {cache:'no-store'});
  if(!resp.ok) throw new Error('HTTP '+resp.status);
  const dati = await resp.json();
  DASH = {
    generato: dati.generato || '',
    temi: (dati.temi && dati.temi.length) ? dati.temi
        : ['chip','data_center','energia','supply_chain','cloud_capacity'],
    // ogni run ottiene data (YYYY-MM-DD) e giorni-fa per il filtro periodo
    run: (dati.run||[]).map(function(r){
      const data = (r.timestamp||'').slice(0,10);
      return Object.assign({}, r, {data: data, giorni: giorniFa(data)});
    })
  };
  return DASH;
}

async function vaiDashboard(){
  TEMA_CORRENTE = null;
  FILTRO_DATE = {dal:'', al:''};
  FILTRO_ONCHANGE = renderDashboard;      // il filtro periodo aggiorna i pannelli
  app.innerHTML = `<section class="view"><main class="crono dash">
      <button class="indietro" onclick="vaiHome()">← Home</button>
      <h2><span class="tema-ic">${iconaOsserva(26)}</span>Osservabilità</h2>
      <p class="sez-nota">Stato delle fonti, costi, deduplica e copertura dei temi — per periodo.</p>
      <div id="dash-corpo"><p class="sez-nota">Caricamento…</p></div>
    </main></section>`;
  window.scrollTo({top:0,behavior:'smooth'});
  try{
    await caricaDashboard();
  }catch(err){
    const c = document.getElementById('dash-corpo');
    if(c) c.innerHTML = '<p class="sez-nota">Metriche non ancora disponibili ('+err.message+'). '
      + 'Vengono registrate a partire dal primo run.</p>';
    return;
  }
  const c = document.getElementById('dash-corpo');
  if(!c) return;
  if(!DASH.run.length){
    c.innerHTML = '<p class="sez-nota">Nessun run registrato finora.</p>';
    return;
  }
  c.innerHTML = `${controlliFiltroData(RANGE_DASH)}<div id="dash-pannelli"></div>`;
  renderDashboard();
}

function renderDashboard(){
  const cont = document.getElementById('dash-pannelli');
  if(!DASH || !cont) return;
  const st = statoFiltroPeriodo();
  const runs = filtraPerPeriodo(DASH.run, st);       // DASH.run è già dal più recente
  const btn = document.querySelector('.btn-azzera');
  if(btn) btn.classList.toggle('nascosto', !filtroPeriodoAttivo(st));
  cont.innerHTML = runs.length
    ? pannelloFonti(runs) + pannelloCosti(runs) + pannelloDedup(runs) + pannelloCopertura(runs)
    : '<p class="sez-nota">Nessun run nel periodo selezionato.</p>';
  attivaEffetti();
}

/* barra orizzontale 0–100% (meter) */
function dashBar(frazione, cls){
  const pct = Math.max(0, Math.min(100, Math.round((frazione||0)*100)));
  return `<div class="dash-bar ${cls||''}"><span style="width:${pct}%"></span></div>`;
}
function statCard(valore, etichetta){
  return `<div class="dash-stat"><div class="ds-val">${valore}</div><div class="ds-lbl">${etichetta}</div></div>`;
}

/* --- pannello STATO FONTI ---------------------------------------------- */
function pannelloFonti(runs){
  const cron = runs.slice().reverse();                       // vecchio -> nuovo (per i dot)
  const ultimo = runs[0];
  // unione dei nomi fonte (l'ultimo run per primo, poi eventuali fonti sparite)
  const nomi = [];
  runs.forEach(r => (r.fonti||[]).forEach(f => { if(!nomi.includes(f.nome)) nomi.push(f.nome); }));
  const koUltimo = (ultimo.fonti||[]).filter(f => f.stato === 'fetch_failed').length;

  const righe = nomi.map(function(nome){
    const serie = cron.map(r => (r.fonti||[]).find(f => f.nome === nome) || null);
    const corr = (ultimo.fonti||[]).find(f => f.nome === nome) || null;
    const falliti = serie.filter(f => f && f.stato === 'fetch_failed').length;
    const dots = serie.map(function(f){
      if(!f) return '<span class="dot dot-na" title="assente"></span>';
      const ok = f.stato === 'ok';
      const tip = f.stato + (f.errore ? ': ' + f.errore.replace(/"/g,'') : '');
      return `<span class="dot ${ok?'dot-ok':'dot-ko'}" title="${tip}"></span>`;
    }).join('');
    const badge = corr
      ? (corr.stato === 'ok' ? '<span class="badge-ok">OK</span>' : '<span class="badge-ko">Fallito</span>')
      : '<span class="badge-na">—</span>';
    const strk = (corr && corr.consecutivi_falliti > 0)
      ? `<span class="dash-strk">${corr.consecutivi_falliti} run consecutivi</span>` : '';
    return `<div class="dash-fonte">
        <div class="df-testa"><span class="df-nome">${nome}</span> ${badge} ${strk}</div>
        <div class="df-serie">${dots}</div>
        <div class="df-conta">${falliti}/${serie.length} run falliti nel periodo</div>
      </div>`;
  }).join('');

  return `<section class="dash-card reveal">
      <div class="dash-tit">${iconaOsserva(16)} Stato fonti</div>
      <div class="dash-stats">
        ${statCard(nomi.length, 'fonti')}
        ${statCard(koUltimo, 'in errore (ultimo run)')}
        ${statCard(runs.length, plurale(runs.length,'run','run'))}
      </div>
      <div class="dash-fonti">${righe}</div>
    </section>`;
}

/* --- pannello COSTI ---------------------------------------------------- */
function pannelloCosti(runs){
  const tot = runs.reduce((a,r)=>({
    p: a.p + r.costo.prompt_tokens, c: a.c + r.costo.completion_tokens, e: a.e + r.costo.costo_stimato
  }), {p:0,c:0,e:0});
  const maxTok = Math.max.apply(null,
    runs.map(r => r.costo.prompt_tokens + r.costo.completion_tokens).concat([1]));
  const righe = runs.map(function(r){
    const tk = r.costo.prompt_tokens + r.costo.completion_tokens;
    return `<div class="dash-run">
        <div class="dr-data">${fmtData(r.data)}</div>
        <div class="dr-bar">${dashBar(tk/maxTok,'bar-cost')}</div>
        <div class="dr-val">${fmtNum(tk)} tok · ${fmtEuro(r.costo.costo_stimato)}</div>
      </div>`;
  }).join('');
  return `<section class="dash-card reveal">
      <div class="dash-tit">${iconaOsserva(16)} Costi</div>
      <div class="dash-stats">
        ${statCard(fmtEuro(tot.e), 'costo stimato')}
        ${statCard(fmtNum(tot.p), 'token input')}
        ${statCard(fmtNum(tot.c), 'token output')}
      </div>
      <div class="dash-runs">${righe}</div>
    </section>`;
}

/* --- pannello DEDUPLICA ------------------------------------------------ */
function pannelloDedup(runs){
  const tot = runs.reduce((a,r)=>({
    racc: a.racc + r.dedup.raccolti,
    pub:  a.pub  + r.dedup.pubblicati,
    dup:  a.dup  + r.dedup.duplicati_esatti + r.dedup.duplicati_fuzzy,
    agg:  a.agg  + r.dedup.aggiornamenti
  }), {racc:0,pub:0,dup:0,agg:0});
  const righe = runs.map(function(r){
    const d = r.dedup;
    const scartati = d.duplicati_esatti + d.duplicati_fuzzy + d.scartati_classificazione;
    return `<div class="dash-run">
        <div class="dr-data">${fmtData(r.data)}</div>
        <div class="dr-bar">${dashBar(d.raccolti ? d.pubblicati/d.raccolti : 0,'bar-pub')}</div>
        <div class="dr-val">${d.pubblicati}/${d.raccolti} pubblicati
          · <span class="mut">${scartati} scartati, ${d.aggiornamenti} agg.</span></div>
      </div>`;
  }).join('');
  return `<section class="dash-card reveal">
      <div class="dash-tit">${iconaOsserva(16)} Deduplica</div>
      <div class="dash-stats">
        ${statCard(fmtNum(tot.racc), 'raccolti')}
        ${statCard(fmtNum(tot.pub), 'pubblicati')}
        ${statCard(fmtNum(tot.dup), 'duplicati scartati')}
        ${statCard(fmtNum(tot.agg), 'inclusi come agg.')}
      </div>
      <div class="dash-runs">${righe}</div>
    </section>`;
}

/* --- pannello COPERTURA TEMI ------------------------------------------- */
function pannelloCopertura(runs){
  const ultimo = runs[0];
  const righe = DASH.temi.map(function(id){
    const conAgg = runs.filter(r =>
      ((r.copertura||[]).find(c => c.tema === id) || {}).stato === 'con_aggiornamenti').length;
    const cUlt = (ultimo.copertura||[]).find(c => c.tema === id) || {};
    return `<div class="dash-cop">
        <div class="dc-testa"><span class="tema-ic">${iconaTema(id,15)}</span>${nomeTema(id)}
          <span class="dc-ult">${cUlt.n_articoli||0} nell'ultimo run</span></div>
        <div class="dc-bar">${dashBar(runs.length ? conAgg/runs.length : 0,'bar-cop')}</div>
        <div class="dc-conta">${conAgg}/${runs.length} run con aggiornamenti</div>
      </div>`;
  }).join('');
  const streak = ultimo.energia_zero_consecutivi || 0;
  const avviso = streak >= 3
    ? `<div class="dash-avviso">⚠ Energia a zero da ${streak} run consecutivi (fonte unica arXiv): controllo manuale.</div>`
    : `<div class="dash-nota-min">Energia a zero da ${streak} run consecutivi.</div>`;
  return `<section class="dash-card reveal">
      <div class="dash-tit">${iconaOsserva(16)} Copertura dei temi</div>
      <div class="dash-cops">${righe}</div>
      ${avviso}
    </section>`;
}

/* --------------------- animazioni / micro-interazioni --------------------- */
function attivaEffetti(){
  // reveal allo scroll
  const io = new IntersectionObserver(es=>es.forEach(e=>{ if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);} }),{threshold:.12});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));

  // leggero tilt 3D delle card al passaggio del mouse
  document.querySelectorAll('[data-tilt]').forEach(card=>{
    card.onmousemove = e=>{
      const r=card.getBoundingClientRect();
      const rx=((e.clientY-r.top)/r.height-.5)*-6, ry=((e.clientX-r.left)/r.width-.5)*6;
      card.style.transform=`perspective(800px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-4px)`;
    };
    card.onmouseleave = ()=> card.style.transform='';
  });
}

caricaDati();
