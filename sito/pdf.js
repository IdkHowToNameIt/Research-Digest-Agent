/* ---------------------------------------------------------------------------
   Esportazione PDF del digest — Fase 1: generazione + download locale.
   Costruisce il PDF lato browser dai DATI STRUTTURATI già in memoria del gruppo
   (tema + giorno) aperto, NON da uno screenshot del DOM: il testo resta
   selezionabile e il file pesa poco. Usa jsPDF vendorizzata (jspdf.umd.min.js,
   nessuna CDN a runtime). Le funzioni globali di app.js usate qui
   (gruppoCorrente, nomeTema, fmtData, fmtLettura, pad2) esistono già a runtime.
--------------------------------------------------------------------------- */
(function(){
  'use strict';

  // Palette coerente col sito, ma su fondo BIANCO (documento da leggere/stampare):
  // testo scuro, accento rosa KVA (#e0506e), secondario grigio (#7a8089).
  const ACCENTO = [224, 80, 110];
  const INK     = [28, 27, 32];
  const MUTED   = [122, 128, 137];
  const RIGA    = [225, 227, 230];   // separatori sottili

  // --- Caratteri renderizzabili dai font standard di jsPDF -------------------
  // I font standard del PDF (Helvetica & co.) sono a BYTE SINGOLO, codifica
  // WinAnsi/cp1252. Se una stringa contiene anche un solo carattere fuori da quel
  // set, jsPDF scrive l'INTERA riga in UTF-16 — ma il font resta a byte singolo,
  // quindi il lettore mostra un byte 0x00 tra una lettera e l'altra: "s o n o
  // s c r i t t e   c o s i", con la riga larga il doppio che sfonda il margine
  // destro e viene TAGLIATA (testo perso, non solo brutto).
  // Nel PDF di esempio del 2026-07-19: 14 righe su 136 (10%), per due soli
  // caratteri prodotti dal modello — U+2011 (trattino unificatore) e U+202F
  // (spazio stretto unificatore). Vedi DECISIONI sez. 16.
  //
  // Scritti come escape \uXXXX di proposito: molti sono invisibili o si
  // confondono con l'ASCII, e come caratteri letterali nel sorgente sarebbero
  // impossibili da rivedere. Questi sono i cp1252 di 0x80-0x9F: non sono Latin-1,
  // ma i font standard del PDF li rendono comunque.
  const EXTRA_CP1252 =
    '\u20AC\u201A\u0192\u201E\u2026\u2020\u2021\u02C6\u2030\u0160' +
    '\u2039\u0152\u017D\u2018\u2019\u201C\u201D\u2022\u2013\u2014' +
    '\u02DC\u2122\u0161\u203A\u0153\u017E\u0178';

  function renderizzabile(ch){
    const c = ch.codePointAt(0);
    return (c <= 0x7F) || (c >= 0xA0 && c <= 0xFF) || EXTRA_CP1252.indexOf(ch) >= 0;
  }

  // Equivalenti sicuri per i caratteri tipografici che il modello usa piu' spesso.
  // Meglio un trattino normale che una riga illeggibile: il senso si conserva.
  const SOSTITUZIONI = {
    '\u2011': '-',  '\u2010': '-', '\u2012': '-', '\u2212': '-',  // trattini
    '\u202F': ' ',  '\u2002': ' ', '\u2003': ' ', '\u2004': ' ',  // spazi tipografici
    '\u2005': ' ',  '\u2007': ' ', '\u2008': ' ', '\u2009': ' ', '\u200A': ' ',
    '\u200B': '',   '\u200C': '',  '\u200D': '',  '\uFEFF': '',   // larghezza zero
    '\u00AD': '',                                                 // soft hyphen
    '\u2044': '/',  '\u2215': '/',
    '\u03BC': '\u00B5',                                 // mu greca -> segno micro
    '\u2248': '~',  '\u2260': '!=', '\u2264': '<=', '\u2265': '>=',
    '\u2192': '->', '\u2190': '<-', '\u21D2': '=>',
    '\u2032': "'",  '\u2033': '"'                       // primo, doppio primo
  };

  // Rende una stringa sicura per i font standard del PDF.
  function sanifica(testo){
    const s = String(testo == null ? '' : testo);
    let out = '';
    for(const ch of s){
      if(renderizzabile(ch)){ out += ch; continue; }
      const sost = SOSTITUZIONI[ch];
      if(sost !== undefined){ out += sost; continue; }
      // Ripiego generico: scompone il carattere e tiene ci\u00f2 che \u00e8 renderizzabile
      // (es. una lettera accentata esotica -> lettera base). Se non resta nulla il
      // carattere sparisce: perdere un simbolo raro \u00e8 meno grave che perdere
      // l'intera riga fuori pagina.
      let acc = '';
      for(const c2 of ch.normalize('NFKD')){ if(renderizzabile(c2)) acc += c2; }
      out += acc;
    }
    return out;
  }

  const LOGO_SRC = 'kva-logo.webp';
  const MM = 0.3528;                  // punti tipografici -> mm (per l'interlinea)

  // Il logo del sito è .webp: jsPDF incorpora solo PNG/JPEG, quindi lo si
  // ridisegna una volta su un <canvas> e lo si esporta in PNG (dataURL). La cache
  // evita di rifarlo a ogni PDF. `false` = logo non disponibile: si prosegue senza.
  let logoCache = null;

  function caricaLogo(){
    if(logoCache !== null) return Promise.resolve(logoCache);
    return new Promise(function(resolve){
      const img = new Image();
      img.onload = function(){
        try{
          const c = document.createElement('canvas');
          c.width = img.naturalWidth || 96;
          c.height = img.naturalHeight || 76;
          c.getContext('2d').drawImage(img, 0, 0);
          logoCache = {dataUrl: c.toDataURL('image/png'), w: c.width, h: c.height};
        }catch(e){ logoCache = false; }   // canvas "tainted" o webp non decodificabile
        resolve(logoCache);
      };
      img.onerror = function(){ logoCache = false; resolve(false); };
      img.src = LOGO_SRC;
    });
  }

  // Nome file: DRA_<tema>_<data>.pdf (solo caratteri sicuri per il filesystem).
  function nomeFile(t, g){
    const pezzo = (s) => String(s || '').replace(/[^a-z0-9_-]+/gi, '-').replace(/^-+|-+$/g, '');
    return 'DRA_' + (pezzo(t.id) || 'digest') + '_' + (pezzo(g.data) || 'giorno') + '.pdf';
  }

  // Geometria pagina A4 (mm) e margini.
  const PW = 210, PH = 297, ML = 18, MR = 18, MT = 16, MB = 18;
  const CW = PW - ML - MR;           // larghezza colonna di testo

  function costruisci(doc, t, g, logo){
    let y = MT;
    const nl = (s) => s * MM * 1.18;   // interlinea per un corpo `s` (pt)

    // va a capo pagina se non c'è spazio per `h` mm sotto il cursore
    function spazio(h){ if(y + h > PH - MB){ doc.addPage(); y = MT; } }

    // paragrafo con a-capo automatico; `x` e larghezza in mm; ritorna nulla (muove y)
    function paragrafo(testo, x, larghezza, size, colore, stile){
      doc.setFont('helvetica', stile || 'normal');
      doc.setFontSize(size);
      doc.setTextColor(colore[0], colore[1], colore[2]);
      const lh = nl(size);
      // sanifica PRIMA di dividere: le larghezze devono essere misurate sul
      // testo che verrà davvero scritto, altrimenti l'a-capo sbaglia i conti.
      const linee = doc.splitTextToSize(sanifica(testo), larghezza);
      for(let i = 0; i < linee.length; i++){
        spazio(lh);
        doc.text(linee[i], x, y);
        y += lh;
      }
    }

    // -------- TESTATA (solo prima pagina): logo + marchio + titolo + sottotitolo
    if(logo && logo.dataUrl){
      const h = 11, w = h * (logo.w / logo.h);
      doc.addImage(logo.dataUrl, 'PNG', ML, y, w, h);
      doc.setFont('helvetica', 'bold'); doc.setFontSize(11);
      doc.setTextColor(ACCENTO[0], ACCENTO[1], ACCENTO[2]);
      doc.text('DRA · Digest Research Agent', ML + w + 4, y + 7);
    }else{
      doc.setFont('helvetica', 'bold'); doc.setFontSize(11);
      doc.setTextColor(ACCENTO[0], ACCENTO[1], ACCENTO[2]);
      doc.text('DRA · Digest Research Agent', ML, y + 7);
    }
    y += 11 + 6;

    // titolo del digest
    paragrafo(g.titolo || 'Digest', ML, CW, 17, INK, 'bold');
    y += 1;

    // riga tema · data · tempo di lettura
    const tema = (typeof nomeTema === 'function') ? nomeTema(t.id) : (t.nome || t.id);
    const data = (typeof fmtData === 'function') ? fmtData(g.data) : (g.data || '');
    const lett = (typeof fmtLettura === 'function') ? fmtLettura(g.minuti) : '';
    let sub = sanifica(tema) + ' · ' + sanifica(data);
    if(lett) sub += ' · ' + sanifica(lett);
    paragrafo(sub, ML, CW, 9.5, MUTED, 'normal');

    // filetto accento sotto la testata
    y += 1.5;
    doc.setDrawColor(ACCENTO[0], ACCENTO[1], ACCENTO[2]); doc.setLineWidth(0.6);
    doc.line(ML, y, PW - MR, y);
    y += 6;

    // -------- VOCI DEL DIGEST
    const articoli = g.articoli || [];
    articoli.forEach(function(a, i){
      // separatore tra le voci (non prima della prima)
      if(i > 0){
        spazio(8);
        doc.setDrawColor(RIGA[0], RIGA[1], RIGA[2]); doc.setLineWidth(0.2);
        doc.line(ML, y, PW - MR, y);
        y += 5;
      }
      // numero (accento) + titolo (scuro, grassetto), allineati; il titolo va a capo
      const numX = ML, titX = ML + 8;
      doc.setFont('helvetica', 'bold'); doc.setFontSize(12.5);
      const lhT = nl(12.5);
      const linee = doc.splitTextToSize(sanifica(a.titolo), CW - 8);
      for(let k = 0; k < linee.length; k++){
        spazio(lhT);
        if(k === 0){
          doc.setTextColor(ACCENTO[0], ACCENTO[1], ACCENTO[2]);
          doc.text((typeof pad2 === 'function') ? pad2(i + 1) : String(i + 1), numX, y);
        }
        doc.setFont('helvetica', 'bold'); doc.setFontSize(12.5);
        doc.setTextColor(INK[0], INK[1], INK[2]);
        doc.text(linee[k], titX, y);
        y += lhT;
      }
      y += 1.5;

      // fonti (con link cliccabili quando presenti), a-capo se serve.
      // Riservo spazio per un massimo di 2 righe, così il flusso non spezza pagina.
      spazio(nl(8.8) * 2);
      y = scriviFonti(doc, a.fonti || [], titX, CW - 8, y, nl);
      y += 1.5;

      // sintesi
      if(a.sintesi) paragrafo(a.sintesi, titX, CW - 8, 10, INK, 'normal');

      // perché conta (etichetta accento + testo)
      if(a.perche){
        y += 1;
        paragrafo('Perché conta', titX, CW - 8, 9, ACCENTO, 'bold');
        paragrafo(a.perche, titX, CW - 8, 10, INK, 'normal');
      }

      // nota editoriale (se presente): corsivo, tono secondario
      if(a.nota){
        y += 1;
        paragrafo('Nota: ' + a.nota, titX, CW - 8, 9, MUTED, 'italic');
      }
      y += 3;
    });

    // -------- PIÈ DI PAGINA su tutte le pagine: marchio + "Pagina i di N"
    const n = doc.getNumberOfPages();
    for(let p = 1; p <= n; p++){
      doc.setPage(p);
      doc.setDrawColor(RIGA[0], RIGA[1], RIGA[2]); doc.setLineWidth(0.2);
      doc.line(ML, PH - MB + 6, PW - MR, PH - MB + 6);
      doc.setFont('helvetica', 'normal'); doc.setFontSize(8);
      doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
      doc.text('DRA — kakashi.ventures', ML, PH - MB + 11);
      const et = 'Pagina ' + p + ' di ' + n;
      doc.text(et, PW - MR - doc.getTextWidth(et), PH - MB + 11);
    }
    return doc;
  }

  // Flusso orizzontale delle fonti con a-capo (max ~2 righe, spazio già riservato
   // dal chiamante). Funzione PURA: disegna da `yStart` e ritorna la nuova y.
  function scriviFonti(doc, fonti, x, larghezza, yStart, nl){
    const size = 8.8, lh = nl(size);
    doc.setFontSize(size);
    let y = yStart, cx = x;
    function acapo(){ y += lh; cx = x + 6; }
    doc.setFont('helvetica', 'bold'); doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]);
    const lbl = 'Fonti: '; doc.text(lbl, cx, y); cx += doc.getTextWidth(lbl);
    doc.setFont('helvetica', 'normal');
    (fonti.length ? fonti : [{nome: '—'}]).forEach(function(f, idx){
      const nome = sanifica(f.nome);
      const sep = idx > 0 ? ' · ' : '';
      const wSep = doc.getTextWidth(sep), wNome = doc.getTextWidth(nome);
      if(cx + wSep + wNome > x + larghezza) acapo();
      if(sep){ doc.setTextColor(MUTED[0], MUTED[1], MUTED[2]); doc.text(sep, cx, y); cx += wSep; }
      if(f.link){
        doc.setTextColor(ACCENTO[0], ACCENTO[1], ACCENTO[2]);
        doc.textWithLink(nome, cx, y, {url: f.link});
      }else{
        doc.setTextColor(INK[0], INK[1], INK[2]);
        doc.text(nome, cx, y);
      }
      cx += wNome;
    });
    return y + lh;
  }

  // Costruisce il documento PDF del gruppo aperto. Condiviso da download e invio email.
  // Ritorna {doc, filename} o lancia se manca la libreria/il gruppo.
  async function creaDocGruppo(){
    const cur = (typeof gruppoCorrente === 'function') ? gruppoCorrente() : null;
    if(!cur || !cur.g || !cur.g.articoli){ throw new Error('Nessun digest aperto.'); }
    const jspdf = window.jspdf || {};
    if(!jspdf.jsPDF){ throw new Error('Componente PDF non disponibile.'); }
    const logo = await caricaLogo();
    const doc = new jspdf.jsPDF({unit: 'mm', format: 'a4'});
    costruisci(doc, cur.t, cur.g, logo);
    return {doc: doc, filename: nomeFile(cur.t, cur.g), cur: cur};
  }

  // "Scarica PDF": genera e scarica in locale.
  async function scaricaPdfGruppoCorrente(ev){
    const btn = ev && ev.currentTarget ? ev.currentTarget : null;
    if(btn){ btn.disabled = true; btn.classList.add('caricando'); }
    try{
      const r = await creaDocGruppo();
      r.doc.save(r.filename);
    }catch(e){
      alert('Non è stato possibile generare il PDF (' + (e && e.message || e) + ').');
    }finally{
      if(btn){ btn.disabled = false; btn.classList.remove('caricando'); }
    }
  }

  // "Invia via email": mostra/nasconde il pannello con il campo indirizzo.
  function apriInvioEmail(){
    const panel = document.getElementById('mail-panel');
    if(!panel) return;
    panel.hidden = !panel.hidden;
    if(!panel.hidden){
      const input = document.getElementById('mail-input');
      if(input) input.focus();
    }
  }

  function statoMail(testo, cls){
    const el = document.getElementById('mail-stato');
    if(!el) return;
    el.textContent = testo || '';
    el.className = 'mail-stato' + (cls ? ' ' + cls : '');
  }

  // Genera il PDF e lo invia al Worker (che inoltra a Resend). Nessun SMTP lato client.
  async function inviaPdfEmail(ev){
    const btn = ev && ev.currentTarget ? ev.currentTarget : null;
    const url = window.DRA_INVIO_EMAIL_URL || '';
    if(!url){ statoMail('Invio email non configurato.', 'ko'); return; }
    const input = document.getElementById('mail-input');
    const email = input ? input.value.trim() : '';
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){
      statoMail('Inserisci un indirizzo email valido.', 'ko');
      if(input) input.focus();
      return;
    }
    if(btn){ btn.disabled = true; btn.classList.add('caricando'); }
    statoMail('Invio in corso…', 'loading');
    try{
      const r = await creaDocGruppo();
      // base64 puro (senza prefisso "data:...;base64,") per l'allegato Resend
      const durl = r.doc.output('datauristring');
      const b64 = durl.substring(durl.indexOf('base64,') + 7);
      const resp = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          email: email,
          filename: r.filename,
          pdf: b64,
          tema: (r.cur.t && r.cur.t.nome) || '',
          data: r.cur.g.data || ''
        })
      });
      let dati = {};
      try{ dati = await resp.json(); }catch(e){}
      if(resp.ok && dati.ok){
        statoMail('Inviato a ' + email + '.', 'ok');
        if(input) input.value = '';
      }else{
        statoMail(dati.errore || 'Invio non riuscito. Riprova.', 'ko');
      }
    }catch(e){
      statoMail('Rete non disponibile. Riprova.', 'ko');
    }finally{
      if(btn){ btn.disabled = false; btn.classList.remove('caricando'); }
    }
  }

  window.scaricaPdfGruppoCorrente = scaricaPdfGruppoCorrente;
  window.apriInvioEmail = apriInvioEmail;
  window.inviaPdfEmail = inviaPdfEmail;
})();
