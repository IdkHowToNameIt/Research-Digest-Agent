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
    TEMI = (dati.temi||[]).map(function(t){
      return {
        id: t.id, nome: t.nome,
        articoli: (t.articoli||[]).map(function(a){
          return {
            titolo: a.titolo,
            fonte: (a.fonti||[]).map(function(f){return f.nome;}).join(' · '),
            fonti: a.fonti||[],
            data: a.data,
            giorni: giorniFa(a.data),
            sintesi: a.sintesi||'',
            perche: a.perche_conta||'',
            nota: a.note||null
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

/* ---------------------------- HOMEPAGE ---------------------------- */
function vaiHome(){
  const conAgg = TEMI.filter(t => t.articoli.some(a => a.giorni <= SOGLIA_SETTIMANA));
  const oggi = fmtData(new Date().toISOString().slice(0,10));

  const nav = TEMI.map(t =>
    `<button class="pill" onclick="vaiTema('${t.id}')">${iconaTema(t.id,15)}${t.nome}</button>`
  ).join('');

  const boxes = conAgg.map(t=>{
    const voci = t.articoli.filter(a=>a.giorni<=SOGLIA_SETTIMANA).map((a)=>{
      const idx = t.articoli.indexOf(a);
      return `<li><a onclick="vaiArticolo('${t.id}',${idx})">${a.titolo}
                <br><small>${a.fonte} · ${fmtData(a.data)}</small></a></li>`;
    }).join('');
    return `<div class="box reveal" data-tilt>
        <h3><span class="tema-ic">${iconaTema(t.id,22)}</span>${t.nome}</h3>
        <ul>${voci}</ul>
        <span class="apri" onclick="vaiTema('${t.id}')">Cronologia ${t.nome} →</span>
      </div>`;
  }).join('');

  const contenuto = boxes || '<p class="sez-nota">Nessun aggiornamento questa settimana.</p>';

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
      <div class="sez-nota">Compaiono solo i temi con novità nella settimana corrente.</div>
      <div class="boxes">${contenuto}</div>
    </main>
  </section>`;
  attivaEffetti();
}

/* ------------------------- CRONOLOGIA TEMA ------------------------ */
function vaiTema(id){
  const t = trovaTema(id);
  const ordinati = t.articoli.map((a,i)=>({a,i})).sort((x,y)=>x.a.giorni-y.a.giorni);
  const nuovi = ordinati.filter(o=>o.a.giorni<=SOGLIA_NUOVO);
  const vecchi = ordinati.filter(o=>o.a.giorni>SOGLIA_NUOVO);

  const voce = (o)=>{
    const a=o.a, nuovo = a.giorni<=SOGLIA_NUOVO;
    return `<div class="voce reveal" onclick="vaiArticolo('${id}',${o.i})">
        <div class="meta"><span class="fonte" style="color:var(--verde);font-weight:600">${a.fonte}</span>
          · ${fmtData(a.data)} ${nuovo?'<span class="badge-nuovo">Nuovo</span>':''}</div>
        <h4>${a.titolo}</h4>
        <div>${(a.sintesi||'').split('. ')[0]}.</div>
      </div>`;
  };

  let corpo = '';
  if(nuovi.length){ corpo += `<div class="etichetta-nuovo">Nuovo aggiornamento</div>` + nuovi.map(voce).join('') + `<hr class="divisore">`; }
  corpo += vecchi.map(voce).join('') || (nuovi.length?'':'<p class="sez-nota">Nessun articolo in archivio per questo tema.</p>');

  app.innerHTML = `<section class="view"><main class="crono">
      <button class="indietro" onclick="vaiHome()">← Home</button>
      <h2>${t.nome} — cronologia</h2>
      ${corpo}
    </main></section>`;
  attivaEffetti();
}

/* --------------------------- ARTICOLO ---------------------------- */
function vaiArticolo(id,i){
  const t = trovaTema(id), a = t.articoli[i];
  app.innerHTML = `<section class="view"><main class="articolo">
      <button class="indietro" onclick="vaiTema('${id}')">← ${t.nome}</button>
      <h1>${a.titolo}</h1>
      <div class="meta"><span class="fonte">${a.fonte}</span> · ${fmtData(a.data)}</div>
      ${a.nota?`<div class="nota">${a.nota}</div>`:''}
      <p style="margin-top:1rem">${a.sintesi}</p>
      <div class="perche"><strong>Perché conta:</strong> ${a.perche}</div>
    </main></section>`;
  window.scrollTo({top:0,behavior:'smooth'});
  attivaEffetti();
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
