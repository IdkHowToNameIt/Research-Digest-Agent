"""Test dei dati del sito web interno (Fase 8, sez. 18).

Nuovo contratto (separazione backend/frontend): il backend NON genera HTML, ma
produce `data.json` (archivio aggregato per tema + soglie) e copia il template del
frontend in index.html. Homepage/cronologia/badge sono generati LATO CLIENT dal
frontend a partire da questi dati.

Si verifica quindi:
- data.json: 5 temi in ordine, articoli completi, soglia badge, aggregazione
  storica più-recente-prima;
- `note_interne` mai presente nei dati del sito (16.7);
- genera_sito copia il template in index.html.
"""
import json
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
    ETICHETTE,
    carica_archivio,
    costruisci_dati,
    genera_sito,
    raccogli_per_tema,
    salva_digest_pubblico,
    temi_con_aggiornamenti,
)


def _art(titolo, url, data="2026-07-09"):
    return Articolo(titolo=titolo, fonti=[Fonte(nome="NVIDIA", link=url)],
                    data=data, sintesi=f"Sintesi di {titolo}.",
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


def _dati(d: Digest, **kw) -> dict:
    return costruisci_dati(d, [d.contenuto_pubblico()], **kw)


# --- struttura di data.json -------------------------------------------------

def test_temi_con_aggiornamenti():
    d = _digest(chip=[_art("A", "https://x/1")])
    assert temi_con_aggiornamenti(d) == [Tema.chip]


def test_dati_cinque_temi_sempre_in_ordine():
    d = _digest(chip=[_art("Chip news", "https://x/1")])
    dati = _dati(d)
    assert [t["id"] for t in dati["temi"]] == [t.value for t in Tema]
    # ogni tema ha id + nome leggibile
    chip = next(t for t in dati["temi"] if t["id"] == "chip")
    assert chip["nome"] == ETICHETTE[Tema.chip]
    assert [a["titolo"] for a in chip["articoli"]] == ["Chip news"]
    # i temi senza aggiornamenti esistono comunque, vuoti
    energia = next(t for t in dati["temi"] if t["id"] == "energia")
    assert energia["articoli"] == []


def test_dati_articolo_completo():
    d = _digest(chip=[_art("Blackwell", "https://x/1")])
    art = _dati(d)["temi"][0]["articoli"][0]
    assert art["titolo"] == "Blackwell"
    assert art["sintesi"] == "Sintesi di Blackwell."
    assert art["perche_conta"] == "Conta perché Blackwell."
    assert art["data"] == "2026-07-09"
    assert art["fonti"] == [{"nome": "NVIDIA", "link": "https://x/1"}]


def test_badge_giorni_nel_json():
    d = _digest(chip=[_art("A", "https://x/1")])
    assert _dati(d, badge_giorni=5)["badge_giorni"] == 5
    assert _dati(d)["settimana_giorni"] == 7


def test_cronologia_storica_multi_run():
    d1 = _digest("2026-06-01", chip=[_art("Vecchio", "https://x/1", data="2026-06-01")])
    d2 = _digest("2026-07-09", chip=[_art("Recente", "https://x/2", data="2026-07-09")])
    archivio = [d1.contenuto_pubblico(), d2.contenuto_pubblico()]
    per_tema = raccogli_per_tema(archivio)
    titoli = [a["titolo"] for a in per_tema[Tema.chip]]
    assert titoli == ["Recente", "Vecchio"]  # più recente prima
    # anche in data.json l'ordine è più-recente-prima
    dati = costruisci_dati(d2, archivio)
    chip = next(t for t in dati["temi"] if t["id"] == "chip")
    assert [a["titolo"] for a in chip["articoli"]] == ["Recente", "Vecchio"]


# --- generazione file (data.json + copia template) --------------------------

def test_genera_sito_scrive_datajson_e_index(tmp_path):
    template = tmp_path / "tpl.html"
    template.write_text("<html>CONCEPT-TEMPLATE fetch('data.json')</html>", encoding="utf-8")
    d = _digest(chip=[_art("A", "https://x/1")])
    scritti = genera_sito(d, [d.contenuto_pubblico()], str(tmp_path / "out"),
                          template_path=str(template))
    out = tmp_path / "out"
    assert (out / "data.json").exists()
    assert (out / "index.html").exists()
    assert "CONCEPT-TEMPLATE" in (out / "index.html").read_text(encoding="utf-8")
    dati = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert dati["temi"][0]["articoli"][0]["titolo"] == "A"
    assert any("data.json" in s for s in scritti)


def test_template_mancante_non_blocca(tmp_path):
    d = _digest(chip=[_art("A", "https://x/1")])
    scritti = genera_sito(d, [d.contenuto_pubblico()], str(tmp_path),
                          template_path=str(tmp_path / "inesistente.html"))
    assert (tmp_path / "data.json").exists()
    assert not (tmp_path / "index.html").exists()
    assert not any("index.html" in s for s in scritti)


# --- note_interne mai nei dati del sito -------------------------------------

def test_note_interne_mai_nei_dati(tmp_path):
    note = [NotaInterna(tipo=TipoNotaInterna.fetch_failed_ripetuto,
                        dettaglio="SEGRETO-AzureKO")]
    d = _digest(chip=[_art("A", "https://x/1")], note=note)
    genera_sito(d, [d.contenuto_pubblico()], str(tmp_path),
                template_path=str(tmp_path / "nope.html"))
    testo = (tmp_path / "data.json").read_text(encoding="utf-8")
    assert "SEGRETO-AzureKO" not in testo
    assert "note_interne" not in testo


def test_salva_e_carica_archivio_esclude_note(tmp_path):
    note = [NotaInterna(tipo=TipoNotaInterna.sezione_a_zero_ripetuta, dettaglio="SEGRETO")]
    d = _digest(chip=[_art("A", "https://x/1")], note=note)
    salva_digest_pubblico(d, str(tmp_path / "arch"))
    archivio = carica_archivio(str(tmp_path / "arch"))
    assert len(archivio) == 1
    assert "note_interne" not in archivio[0]
    assert "SEGRETO" not in str(archivio[0])
