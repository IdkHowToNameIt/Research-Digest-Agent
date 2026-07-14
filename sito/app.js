/* ---------------------------------------------------------------------------
   App del sito interno: legge i dati REALI da data.json (prodotto dal backend)
   e genera lato client le pagine — homepage, cronologia per tema, articolo.
   Le date degli articoli sono assolute (YYYY-MM-DD): da esse si derivano la
   soglia "Nuovo aggiornamento" (badge_giorni) e la vista "questa settimana"
   (settimana_giorni), entrambe lette da data.json.
--------------------------------------------------------------------------- */
let TEMI = [];
let SOGLIA_NUOVO = 2;      // giorni: badge "Nuovo aggiornamento" (sovrascritto da data.json)
let SOGLIA_SETTIMANA = 7;  // giorni: rientra nel digest "di questa settimana"
let TEMA_CORRENTE = null;    // id del tema nella vista lista-gruppi (per i filtri data)
let GRUPPO_CORRENTE = null;  // {id, data} nella vista dettaglio (per il filtro fonte)
const MESI = ["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"];

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

/* --------- caricamento dei dati reali (data.json, accanto a index.html) --------- */
async function caricaDati(){
  try{
    const resp = await fetch('data.json', {cache:'no-store'});
    if(!resp.ok) throw new Error('HTTP '+resp.status);
    const dati = await resp.json();
    if(dati.badge_giorni != null) SOGLIA_NUOVO = dati.badge_giorni;
    if(dati.settimana_giorni != null) SOGLIA_SETTIMANA = dati.settimana_giorni;
    const mapArt = function(a){
      return {
        titolo: a.titolo,
        fonte: (a.fonti||[]).map(function(f){return f.nome;}).join(' · '),
        fonti: a.fonti||[],
        data: a.data,
        sintesi: a.sintesi||'',
        perche: a.perche_conta||'',
        nota: a.note||null
      };
    };
    TEMI = (dati.temi||[]).map(function(t){
      return {
        id: t.id, nome: t.nome,
        // gruppi = notizie dello stesso giorno unite sotto un titolo riassuntivo
        gruppi: (t.gruppi||[]).map(function(g){
          return {
            data: g.data,
            giorni: giorniFa(g.data),
            titolo: g.titolo||'',
            articoli: (g.articoli||[]).map(mapArt)
          };
        })
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
  const recenti = t.gruppi.filter(g => g.giorni <= SOGLIA_SETTIMANA);
  if(!recenti.length) return '';
  const g0 = recenti[0];                                   // più recente (backend ordina desc)
  const nuovo = g0.giorni <= SOGLIA_NUOVO;
  const nNews = recenti.reduce((s,g)=>s+g.articoli.length, 0);
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
        <label>Dal <input type="date" id="filtro-dal" oninput="renderListaGruppi()"></label>
        <label>Al <input type="date" id="filtro-al" oninput="renderListaGruppi()"></label>
      </div>
    </div>`;
}

function attivaRange(el){
  el.parentElement.querySelectorAll('.pill-f').forEach(p=>p.classList.remove('attivo'));
  el.classList.add('attivo');
  renderListaGruppi();
}

function renderListaGruppi(){
  const t = trovaTema(TEMA_CORRENTE);
  const cont = document.getElementById('lista-gruppi');
  if(!t || !cont) return;
  const pill = document.querySelector('.filtro-range .pill-f.attivo');
  const rg = (pill && pill.dataset.giorni !== 'all') ? Number(pill.dataset.giorni) : null;
  const dal = (document.getElementById('filtro-dal')||{}).value || '';
  const al = (document.getElementById('filtro-al')||{}).value || '';
  let gruppi = t.gruppi.filter(g=>{
    if(rg != null && g.giorni > rg) return false;
    if(dal && !(g.data && g.data >= dal)) return false;
    if(al && !(g.data && g.data <= al)) return false;
    return true;
  });
  cont.innerHTML = gruppi.length
    ? gruppi.map(g=>cardGruppo(t.id, g)).join('')
    : '<p class="sez-nota">Nessun aggiornamento per il periodo selezionato.</p>';
  attivaEffetti();
}

function vaiTema(id){
  const t = trovaTema(id);
  TEMA_CORRENTE = id;
  app.innerHTML = `<section class="view"><main class="crono">
      <button class="indietro" onclick="vaiHome()">← Home</button>
      <h2><span class="tema-ic">${iconaTema(t.id,26)}</span>${t.nome}</h2>
      ${t.gruppi.length ? controlliFiltroData()
        : '<p class="sez-nota">Nessun articolo in archivio per questo tema.</p>'}
      <div id="lista-gruppi"></div>
    </main></section>`;
  renderListaGruppi();
  window.scrollTo({top:0,behavior:'smooth'});
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
