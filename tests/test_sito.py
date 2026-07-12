"""Test del sito web interno (Fase 8, sez. 18).

- homepage: box SOLO per i temi con aggiornamenti nella settimana, navigazione ai
  5 temi, box centrati come gruppo (18.2);
- cronologia per tema con storico completo (18.3);
- badge "nuovo aggiornamento" calcolato LATO CLIENT, non in generazione (18.3);
- `note_interne` mai presente nel sito (16.7).
"""
from pathlib import Path

from src.schemas import (
    Articolo,
    Digest,
    Fonte,
    NotaInterna,
    Sezione,
    Stato,
    Tema,
    TipoNotaInterna,
    sezione_vuota,
)
from src.consegna.sito import (
    carica_archivio,
    genera_sito,
    raccogli_per_tema,
    salva_digest_pubblico,
    temi_con_aggiornamenti,
)


def _art(titolo, url, tema="chip"):
    return Articolo(titolo=titolo, fonti=[Fonte(nome="NVIDIA", link=url)],
                    data="2026-07-09", sintesi=f"Sintesi di {titolo}.",
                    perche_conta=f"Conta perché {titolo}.")


def _digest(data="2026-07-09", chip=None, cloud=None, note=None) -> Digest:
    sezioni = [sezione_vuota(t) for t in Tema]
    mapa = {Tema.chip: chip or [], Tema.cloud_capacity: cloud or []}
    out = []
    for s in sezioni:
        arts = mapa.get(s.tema)
        if arts:
            out.append(Sezione(tema=s.tema, stato=Stato.con_aggiornamenti, articoli=arts))
        else:
            out.append(s)
    return Digest(data_generazione=data, sezioni=out, note_interne=note or [])


def _leggi_tutto(d: Path) -> str:
    return "\n".join(f.read_text(encoding="utf-8") for f in d.glob("*.html"))


# --- homepage ---------------------------------------------------------------

def test_temi_con_aggiornamenti():
    d = _digest(chip=[_art("A", "https://x/1")])
    assert temi_con_aggiornamenti(d) == [Tema.chip]


def test_homepage_box_solo_per_temi_aggiornati(tmp_path):
    d = _digest(chip=[_art("Chip news", "https://x/1")])
    genera_sito(d, [d.contenuto_pubblico()], str(tmp_path))
    home = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Chip news" in home
    # nessun box per temi senza aggiornamenti (es. energia non compare come box)
    assert "class='box'" in home
    assert home.count("class='box'") == 1
    # ma la navigazione include tutti e 5 i temi
    for t in Tema:
        assert f"tema-{t.value}.html" in home


def test_homepage_box_centrati(tmp_path):
    d = _digest(chip=[_art("A", "https://x/1")])
    genera_sito(d, [d.contenuto_pubblico()], str(tmp_path))
    home = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "justify-content:center" in home  # box centrati come gruppo (18.2)


# --- cronologia per tema + pagine articolo ----------------------------------

def test_pagine_tema_e_articolo_generate(tmp_path):
    d = _digest(chip=[_art("Blackwell", "https://x/1"), _art("Rubin", "https://x/2")])
    scritti = genera_sito(d, [d.contenuto_pubblico()], str(tmp_path))
    assert (tmp_path / "tema-chip.html").exists()
    # 5 pagine tema + index + 2 articoli
    assert any("articolo-" in s for s in scritti)
    tema = (tmp_path / "tema-chip.html").read_text(encoding="utf-8")
    assert "Blackwell" in tema and "Rubin" in tema


def test_pagina_articolo_contiene_sintesi_e_perche(tmp_path):
    d = _digest(chip=[_art("Blackwell", "https://x/1")])
    genera_sito(d, [d.contenuto_pubblico()], str(tmp_path))
    art_files = list(tmp_path.glob("articolo-*.html"))
    assert len(art_files) == 1
    testo = art_files[0].read_text(encoding="utf-8")
    assert "Sintesi di Blackwell." in testo
    assert "Perché conta:" in testo


def test_cronologia_storica_multi_run(tmp_path):
    d1 = _digest("2026-06-01", chip=[_art("Vecchio", "https://x/1")])
    d2 = _digest("2026-07-09", chip=[_art("Recente", "https://x/2")])
    archivio = [d1.contenuto_pubblico(), d2.contenuto_pubblico()]
    per_tema = raccogli_per_tema(archivio)
    titoli = [a["titolo"] for a in per_tema[Tema.chip]]
    assert titoli == ["Recente", "Vecchio"]  # piu' recente prima


# --- badge lato client ------------------------------------------------------

def test_badge_calcolato_lato_client(tmp_path):
    d = _digest(chip=[_art("A", "https://x/1")])
    genera_sito(d, [d.contenuto_pubblico()], str(tmp_path), badge_giorni=2)
    tema = (tmp_path / "tema-chip.html").read_text(encoding="utf-8")
    # il calcolo avviene in JS lato client (Date.now), non in generazione pagina
    assert "Date.now()" in tema
    assert "2*24*60*60" in tema
    assert "data-ts=" in tema
    # l'etichetta "Nuovo aggiornamento" esiste solo dentro lo <script> (client-side),
    # non come markup statico pre-renderizzato attorno agli articoli
    prima_script = tema.split("<script>")[0]
    assert "Nuovo aggiornamento" not in prima_script


def test_badge_giorni_configurabile(tmp_path):
    d = _digest(chip=[_art("A", "https://x/1")])
    genera_sito(d, [d.contenuto_pubblico()], str(tmp_path), badge_giorni=5)
    tema = (tmp_path / "tema-chip.html").read_text(encoding="utf-8")
    assert "5*24*60*60" in tema


# --- note_interne mai nel sito ----------------------------------------------

def test_note_interne_mai_nel_sito(tmp_path):
    note = [NotaInterna(tipo=TipoNotaInterna.fetch_failed_ripetuto,
                        dettaglio="SEGRETO-AzureKO")]
    d = _digest(chip=[_art("A", "https://x/1")], note=note)
    genera_sito(d, [d.contenuto_pubblico()], str(tmp_path))
    tutto = _leggi_tutto(tmp_path)
    assert "SEGRETO-AzureKO" not in tutto
    assert "note_interne" not in tutto


def test_salva_e_carica_archivio_esclude_note(tmp_path):
    note = [NotaInterna(tipo=TipoNotaInterna.sezione_a_zero_ripetuta, dettaglio="SEGRETO")]
    d = _digest(chip=[_art("A", "https://x/1")], note=note)
    salva_digest_pubblico(d, str(tmp_path / "arch"))
    archivio = carica_archivio(str(tmp_path / "arch"))
    assert len(archivio) == 1
    assert "note_interne" not in archivio[0]
    assert "SEGRETO" not in str(archivio[0])
