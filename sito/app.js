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

/* carica (una volta) il dettaglio completo di un tema: tema-<id>.json.
   Il token ?v=<generato> permette al browser di cachearlo e riscaricarlo solo
   quando cambia il run (vedi cache-busting lato backend). */
async function caricaTema(t){
  if(t.gruppi) return t.gruppi;   // già in cache di sessione
  const url = t.file + (GENERATO ? ('?v=' + encodeURIComponent(GENERATO)) : '');
  const resp = await fetch(url);
  if(!resp.ok) throw new Error('HTTP '+resp.status);
  const dett = await resp.json();
  t.gruppi = (dett.gruppi||[]).map(function(g){
    return {
      data: g.data,
      giorni: giorniFa(g.data),
      titolo: g.titolo||'',
      articoli: (g.articoli||[]).map(mapArt)
    };
  });
  return t.gruppi;
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

function plurale(n, uno, molti){ return n===1 ? uno : molti; }
function pad2(n){ return String(n).padStart(2,'0'); }

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
   Box auto-centrati (uno per tema con novità nella settimana). Ogni box mostra
   il gruppo più recente del tema (titolo riassuntivo + data); il click porta
   alla lista dei gruppi del tema. */
function boxTema(t){
  // usa i gruppi recenti dell'indice (t.recenti), non il dettaglio (non ancora caricato)
  const recenti = t.recenti.filter(g => g.giorni <= SOGLIA_SETTIMANA);
  if(!recenti.length) return '';
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
  ).join('');

  const boxes = TEMI.map(boxTema).join('');
  const contenuto = boxes
    ? `<div class="boxes">${boxes}</div>`
    : '<p class="sez-nota">Nessun aggiornamento questa settimana.</p>';

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
      <div class="sez-nota">Un box per tema con novità: le notizie dello stesso giorno sono un unico digest.</div>
      ${contenuto}
    </main>
  </section>`;
  attivaEffetti();
}

/* ------------------- LISTA GRUPPI DI UN TEMA ---------------------
   Un gruppo per giorno, rappresentato dal titolo riassuntivo; il click apre il
   dettaglio. In cima, filtri per DATA (periodo rapido + intervallo dal/al). */
function cardGruppo(id, g){
  const nuovo = g.giorni <= SOGLIA_NUOVO;
  const n = g.articoli.length;
  const preview = n>1
    ? `<ul class="preview">${g.articoli.slice(0,3).map(a=>`<li>${a.titolo}</li>`).join('')}
         ${n>3?`<li class="piu">…e altre ${n-3}</li>`:''}</ul>` : '';
  return `<div class="gruppo-card reveal" onclick="vaiGruppo('${id}','${g.data}')">
      <div class="meta">${fmtData(g.data)} ${nuovo?'<span class="badge-nuovo">Nuovo</span>':''}
        · ${n} ${plurale(n,'aggiornamento','aggiornamenti')}</div>
      <h4>${g.titolo}</h4>
      ${preview}
      <span class="apri">Apri il digest del giorno →</span>
    </div>`;
}

function controlliFiltroData(){
  const range = [['all','Tutte'],['7','7 giorni'],['30','30 giorni'],['90','90 giorni']];
  const pills = range.map((r,i)=>
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
  renderListaGruppi();
}

function azzeraFiltriData(){
  FILTRO_DATE = {dal:'', al:''};
  PAGINA = 1;
  aggiornaCampiData();
  chiudiCalendario();
  document.querySelectorAll('.filtro-range .pill-f').forEach(p=>
    p.classList.toggle('attivo', p.dataset.giorni === 'all'));   // torna a "Tutte"
  renderListaGruppi();
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
  renderListaGruppi();
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
  const pill = document.querySelector('.filtro-range .pill-f.attivo');
  const rg = (pill && pill.dataset.giorni !== 'all') ? Number(pill.dataset.giorni) : null;
  const dal = FILTRO_DATE.dal, al = FILTRO_DATE.al;
  let gruppi = t.gruppi.filter(g=>{
    if(rg != null && g.giorni > rg) return false;
    if(dal && !(g.data && g.data >= dal)) return false;
    if(al && !(g.data && g.data <= al)) return false;
    return true;
  });
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
  if(btn) btn.classList.toggle('nascosto', !(rg != null || dal || al));
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

function vaiGruppo(id, data){
  const t = trovaTema(id), g = t.gruppi.find(x=>x.data===data);
  if(!g) return vaiTema(id);
  GRUPPO_CORRENTE = {id, data};
  const nuovo = g.giorni <= SOGLIA_NUOVO;
  const n = g.articoli.length;
  const fonti = [...new Set(g.articoli.map(a=>a.fonte).filter(Boolean))];
  const filtro = fonti.length > 1 ? controlliFiltroFonte(fonti) : '';
  app.innerHTML = `<section class="view"><main class="crono report">
      <button class="indietro" onclick="vaiTema('${id}')">← ${t.nome}</button>
      <div class="giorno-testata">
        <h2>${g.titolo}</h2>
        <div class="giorno-sub"><span class="tag">${iconaTema(t.id,13)}${t.nome}</span>
          · ${fmtData(g.data)} ${nuovo?'<span class="badge-nuovo">Nuovo</span>':''}
          · ${n} ${plurale(n,'aggiornamento','aggiornamenti')}</div>
      </div>
      ${filtro}
      <div class="digest-layout">
        <aside id="digest-indice" class="digest-indice"></aside>
        <div id="digest-lettura" class="digest-lettura"></div>
      </div>
    </main></section>`;
  renderArticoliGruppo();
  window.scrollTo({top:0,behavior:'smooth'});
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
