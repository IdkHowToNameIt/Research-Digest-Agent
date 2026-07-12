"""Generatore del sito web interno (sez. 18).

Sito interno/privato, senza login. Presenta articoli individuali raggruppati per
tema (18.1). Genera:
- index.html: homepage con box SOLO per i temi con aggiornamenti nella settimana
  corrente (18.2), navigazione ai 5 temi, box centrati come gruppo;
- tema-<tema>.html: cronologia storica completa del tema (18.3);
- articolo-<id>.html: una pagina per articolo (sintesi + perche' conta).

Il badge "nuovo aggiornamento" (soglia configurabile, default 2 giorni) e'
calcolato LATO CLIENT via JavaScript (CLAUDE.md / 18.3): la generazione della
pagina NON marca staticamente gli articoli come nuovi.

`note_interne` non compare MAI nel sito (16.7): si lavora sul contenuto pubblico.
Lo stile visivo (colori, logo) e' volutamente minimale: rimandato (sez. 18.2).
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from ..schemas import TEMI_ORDINE, Digest, Stato, Tema

ETICHETTE = {
    Tema.chip: "Chip",
    Tema.data_center: "Data center",
    Tema.energia: "Energia",
    Tema.supply_chain: "Supply chain",
    Tema.cloud_capacity: "Cloud capacity",
}

BADGE_GIORNI_DEFAULT = 2

_CSS = """
:root{--bg:#fff;--fg:#111;--muted:#666;--bd:#ddd}
@media (prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--muted:#aaa;--bd:#333}}
body{background:var(--bg);color:var(--fg);font-family:system-ui,sans-serif;margin:0;padding:1.5rem;line-height:1.5}
header{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--bd);padding-bottom:.75rem}
.logo{font-weight:700}
nav{display:flex;flex-wrap:wrap;gap:.5rem;justify-content:center;margin:1rem 0}
nav a{border:1px solid var(--bd);border-radius:999px;padding:.35rem .9rem;text-decoration:none;color:var(--fg)}
/* box homepage: sempre centrati come gruppo, 1-4 su una riga, 5 su due righe centrate */
.boxes{display:flex;flex-wrap:wrap;justify-content:center;gap:1rem;margin-top:1rem}
.box{border:1px solid var(--bd);border-radius:12px;padding:1rem;min-width:220px;max-width:320px;flex:0 1 260px}
.box h2{margin:.2rem 0 .6rem}
.muted{color:var(--muted)}
.divisore{border:0;border-top:2px dashed var(--bd);margin:1.5rem 0}
article{border-bottom:1px solid var(--bd);padding:1rem 0}
""".strip()


def _badge_js(soglia_giorni: int) -> str:
    """JS che, LATO CLIENT, evidenzia gli articoli pubblicati entro la soglia dal
    momento della visita, spostandoli in cima sotto "Nuovo aggiornamento"."""
    return (
        "<script>(function(){"
        f"var SOGLIA={soglia_giorni}*24*60*60*1000;"
        "var ora=Date.now();"
        "document.querySelectorAll('[data-cronologia]').forEach(function(cont){"
        "var nuovi=[],vecchi=[];"
        "cont.querySelectorAll('[data-ts]').forEach(function(el){"
        "var t=Date.parse(el.getAttribute('data-ts'));"
        "if(!isNaN(t)&&(ora-t)<=SOGLIA){nuovi.push(el);}else{vecchi.push(el);}});"
        "if(nuovi.length){var h=document.createElement('h3');h.textContent='Nuovo aggiornamento';"
        "cont.prepend(document.createElement('hr'));"
        "vecchi.forEach(function(e){cont.appendChild(e);});"
        "var div=document.createElement('hr');div.className='divisore';"
        "cont.insertBefore(div,vecchi[0]||null);"
        "nuovi.reverse().forEach(function(e){cont.prepend(e);});"
        "cont.prepend(h);}"
        "});})();</script>"
    )


def slug(testo: str) -> str:
    s = re.sub(r"[^\w\s-]", "", testo.lower()).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:60].strip("-") or "articolo"


def _id_articolo(art_dict: dict) -> str:
    link = (art_dict.get("fonti") or [{}])[0].get("link", "")
    base = f"{art_dict.get('titolo','')}-{link}"
    import hashlib
    return slug(art_dict.get("titolo", "")) + "-" + hashlib.sha1(base.encode()).hexdigest()[:8]


def _pagina(titolo: str, corpo: str, badge_js: str = "") -> str:
    return (
        "<!doctype html><html lang='it'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(titolo)}</title><style>{_CSS}</style></head><body>"
        "<header><span>Digest Research Agent</span>"
        "<span class='logo'>DRA</span></header>"
        f"{corpo}{badge_js}</body></html>"
    )


def _nav() -> str:
    voci = "".join(
        f"<a href='tema-{t.value}.html'>{html.escape(ETICHETTE[t])}</a>" for t in TEMI_ORDINE
    )
    return f"<nav>{voci}</nav>"


def temi_con_aggiornamenti(digest: Digest) -> list[Tema]:
    """Temi con stato con_aggiornamenti nel digest corrente (per i box homepage)."""
    return [s.tema for s in digest.sezioni if s.stato is Stato.con_aggiornamenti and s.articoli]


def raccogli_per_tema(archivio: list[dict]) -> dict[Tema, list[dict]]:
    """Aggrega gli articoli pubblici dell'archivio per tema, piu' recenti prima.

    `archivio` = lista di digest pubblici (dict, es. Digest.contenuto_pubblico()),
    ciascuno con `data_generazione`. Ogni articolo eredita quel timestamp (`_ts`).
    """
    per_tema: dict[Tema, list[dict]] = {t: [] for t in Tema}
    for pub in sorted(archivio, key=lambda d: d.get("data_generazione", ""), reverse=True):
        ts = pub.get("data_generazione", "")
        for sez in pub.get("sezioni", []):
            try:
                tema = Tema(sez.get("tema"))
            except ValueError:
                continue
            for art in sez.get("articoli", []):
                item = dict(art)
                item["_ts"] = ts
                per_tema[tema].append(item)
    return per_tema


def _card_articolo(art: dict, con_link: bool = True) -> str:
    titolo = html.escape(art.get("titolo", ""))
    ts = html.escape(art.get("_ts", art.get("data", "")))
    idf = _id_articolo(art)
    testa = f"<a href='articolo-{idf}.html'>{titolo}</a>" if con_link else titolo
    return (
        f"<article data-ts='{ts}'><h3 style='margin:.2rem 0'>{testa}</h3>"
        f"<div class='muted'>{ts}</div></article>"
    )


def _pagina_articolo(art: dict) -> str:
    titolo = html.escape(art.get("titolo", ""))
    fonti = " · ".join(
        f"<a href='{html.escape(f.get('link',''))}'>{html.escape(f.get('nome',''))}</a>"
        for f in art.get("fonti", [])
    )
    nota = art.get("note")
    corpo = [
        _nav(),
        f"<h1>{titolo}</h1>",
        f"<div class='muted'>Fonti: {fonti} — {html.escape(art.get('data',''))}</div>",
    ]
    if nota:
        corpo.append(f"<p class='muted'>{html.escape(nota)}</p>")
    corpo.append(f"<p>{html.escape(art.get('sintesi',''))}</p>")
    corpo.append(f"<p><strong>Perché conta:</strong> {html.escape(art.get('perche_conta',''))}</p>")
    return _pagina(titolo, "".join(corpo))


def genera_sito(
    digest_corrente: Digest,
    archivio: list[dict],
    out_dir: str,
    badge_giorni: int = BADGE_GIORNI_DEFAULT,
) -> list[str]:
    """Genera i file del sito e restituisce i percorsi scritti."""
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    scritti: list[str] = []
    per_tema = raccogli_per_tema(archivio)

    # --- homepage: box solo per i temi con aggiornamenti nella settimana ------
    aggiornati = temi_con_aggiornamenti(digest_corrente)
    boxes = []
    for sez in digest_corrente.sezioni:
        if sez.tema not in aggiornati:
            continue  # mai box per temi senza aggiornamenti (18.2)
        voci = "".join(
            f"<li><a href='articolo-{_id_articolo(a.model_dump(mode='json'))}.html'>"
            f"{html.escape(a.titolo)}</a></li>"
            for a in sez.articoli
        )
        boxes.append(f"<section class='box'><h2>{html.escape(ETICHETTE[sez.tema])}</h2><ul>{voci}</ul></section>")
    corpo_home = [
        _nav(),
        "<h1>Digest Research Agent</h1>",
    ]
    if boxes:
        corpo_home.append(f"<div class='boxes'>{''.join(boxes)}</div>")
    else:
        corpo_home.append("<p class='muted'>Nessun aggiornamento questa settimana.</p>")
    (base / "index.html").write_text(_pagina("Digest Research Agent", "".join(corpo_home)), encoding="utf-8")
    scritti.append(str(base / "index.html"))

    # --- pagine cronologia per tema (18.3) + pagine articolo ------------------
    articoli_visti: dict[str, dict] = {}
    for tema in TEMI_ORDINE:
        articoli = per_tema.get(tema, [])
        cronologia = "".join(_card_articolo(a) for a in articoli)
        corpo = [
            _nav(),
            f"<h1>{html.escape(ETICHETTE[tema])} — cronologia</h1>",
        ]
        if articoli:
            corpo.append(f"<div data-cronologia>{cronologia}</div>")
        else:
            corpo.append("<p class='muted'>Nessun articolo in archivio per questo tema.</p>")
        pagina = _pagina(ETICHETTE[tema], "".join(corpo), badge_js=_badge_js(badge_giorni))
        (base / f"tema-{tema.value}.html").write_text(pagina, encoding="utf-8")
        scritti.append(str(base / f"tema-{tema.value}.html"))
        for a in articoli:
            articoli_visti[_id_articolo(a)] = a

    for idf, art in articoli_visti.items():
        (base / f"articolo-{idf}.html").write_text(_pagina_articolo(art), encoding="utf-8")
        scritti.append(str(base / f"articolo-{idf}.html"))

    return scritti


def carica_archivio(dir_archivio: str) -> list[dict]:
    """Carica tutti i digest pubblici (JSON) salvati in `dir_archivio`."""
    p = Path(dir_archivio)
    if not p.exists():
        return []
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(p.glob("*.json"))]


def salva_digest_pubblico(digest: Digest, dir_archivio: str) -> str:
    """Salva il contenuto pubblico del digest (senza note_interne) come JSON."""
    p = Path(dir_archivio)
    p.mkdir(parents=True, exist_ok=True)
    nome = f"{digest.data_generazione}.json"
    percorso = p / nome
    percorso.write_text(
        json.dumps(digest.contenuto_pubblico(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(percorso)
