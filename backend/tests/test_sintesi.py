"""Test di sintesi e assemblaggio (Fase 6). Le chiamate al modello sono mockate.

Basati sui criteri editoriali (sez. 14) e sullo schema (16.6/16.7):
- grounding: metadati reali del candidato, il modello non cambia URL/titolo;
- arXiv: formula di apertura nel prompt + nota preprint aggiunta dal codice (14.8);
- fonti senza estratto: sintesi minima dal titolo (14.6);
- 5 sezioni fisse, il modello non viene invocato per le sezioni vuote (15/16.6).
"""
from src.modello.prompts import (
    APERTURA_ARXIV,
    MAX_ESTRATTO_CHARS,
    NOTA_PREPRINT,
    prompt_sintesi,
)
from src.schemas import Articolo, Stato, Tema
from src.modello.sintesi import (
    assembla_digest,
    sintetizza_candidato,
    sintetizza_titolo_gruppo,
)
from src.raccolta.fetch import Candidato


def _cand(titolo="Titolo reale", estratto="Un estratto con dati.", tema="chip",
          fonte="NVIDIA Blog", url="https://reale/x"):
    return Candidato(titolo=titolo, url=url, fonte=fonte, tema=tema,
                     data="2026-07-09", estratto=estratto)


def _mock_genera(risposta):
    def genera(prompt):
        genera.prompts.append(prompt)
        return dict(risposta)
    genera.prompts = []
    return genera


# --- prompt / criteri editoriali --------------------------------------------

def test_prompt_contiene_regole_di_grounding_e_stile():
    p = prompt_sintesi(_cand())
    assert "SOLO" in p          # usa solo le informazioni fornite
    assert "italiano" in p.lower()
    assert "3-5 frasi" in p


def test_prompt_tronca_estratto_lungo_per_limite_tpm():
    # rete di sicurezza contro il 413 "request too large" del free tier: un
    # estratto enorme (fonte con troncamento null) viene tagliato nel prompt.
    lungo = "dato. " * 4000  # ~24000 char, oltre il tetto
    p = prompt_sintesi(_cand(estratto=lungo))
    assert "[…]" in p                        # marcatore di taglio presente
    assert len(p) < len(lungo)               # il prompt non contiene tutto l'estratto
    # l'estratto nel prompt non supera il tetto (piu' il breve marcatore)
    assert p.count("dato.") * 6 <= MAX_ESTRATTO_CHARS + 10


def test_prompt_non_tronca_estratto_corto():
    p = prompt_sintesi(_cand(estratto="Estratto breve e completo."))
    assert "[…]" not in p
    assert "Estratto breve e completo." in p


def test_prompt_arxiv_include_formula_apertura():
    p = prompt_sintesi(_cand(tema="energia", fonte="arXiv (energia x AI)"))
    assert APERTURA_ARXIV in p


def test_prompt_non_arxiv_senza_formula():
    p = prompt_sintesi(_cand(tema="chip"))
    assert APERTURA_ARXIV not in p


# --- grounding: metadati reali, non del modello -----------------------------

def test_sintetizza_usa_link_reale_ignora_url_del_modello():
    c = _cand(url="https://reale/x")
    genera = _mock_genera({"titolo": "Titolo in italiano", "sintesi": "Testo modello.",
                           "perche_conta": "Conta.", "url": "https://inventato/evil"})
    a = sintetizza_candidato(c, genera)
    assert a.fonti[0].link == "https://reale/x"     # link SEMPRE reale, mai del modello
    assert a.titolo == "Titolo in italiano"          # titolo = riscrittura italiana del modello
    assert a.sintesi == "Testo modello."
    assert a.perche_conta == "Conta."


def test_titolo_ripiega_su_reale_se_modello_non_lo_da():
    c = _cand(titolo="Real English Title")
    genera = _mock_genera({"sintesi": "S.", "perche_conta": "P."})  # niente "titolo"
    a = sintetizza_candidato(c, genera)
    assert a.titolo == "Real English Title"


def test_sintetizza_arxiv_aggiunge_nota_preprint():
    c = _cand(tema="energia", fonte="arXiv")
    genera = _mock_genera({"sintesi": f"{APERTURA_ARXIV} ...", "perche_conta": "Conta."})
    a = sintetizza_candidato(c, genera)
    assert a.note == NOTA_PREPRINT


def test_sintetizza_demo_senza_modello():
    c = _cand(estratto="Estratto informativo.")
    a = sintetizza_candidato(c, genera=None)   # modalita' demo
    assert a.sintesi == "Estratto informativo."
    assert a.perche_conta                        # mai vuoto


def test_sintesi_minima_da_titolo_se_estratto_vuoto_in_demo():
    c = _cand(titolo="Solo titolo AMD", estratto="")
    a = sintetizza_candidato(c, genera=None)
    assert a.sintesi == "Solo titolo AMD"


# --- assemblaggio: 5 sezioni fisse ------------------------------------------

def test_assembla_cinque_sezioni_e_stati_corretti():
    gruppi = {Tema.chip: [_cand(url="https://a/1")], Tema.energia: [_cand(tema="energia", url="https://a/2")]}
    genera = _mock_genera({"sintesi": "S.", "perche_conta": "P."})
    d = assembla_digest(gruppi, genera, data_generazione="2026-07-09")
    assert len(d.sezioni) == 5
    assert d.sezione(Tema.chip).stato is Stato.con_aggiornamenti
    assert d.sezione(Tema.data_center).stato is Stato.nessun_aggiornamento


def test_modello_non_invocato_per_sezioni_vuote():
    gruppi = {Tema.chip: [_cand(url="https://a/1")]}   # solo chip ha materiale
    genera = _mock_genera({"sintesi": "S.", "perche_conta": "P."})
    assembla_digest(gruppi, genera, data_generazione="2026-07-09")
    # una sola chiamata: solo l'unico articolo (nessuna chiamata per le 4 sezioni vuote)
    assert len(genera.prompts) == 1


# --- raggruppamento per giorno + titolo di gruppo ---------------------------

def test_gruppo_singolo_articolo_titolo_uguale_articolo():
    # un solo articolo nel giorno: il titolo del gruppo è quello dell'articolo,
    # senza chiamata extra al modello.
    gruppi = {Tema.chip: [_cand(titolo="Uno", url="https://a/1")]}
    genera = _mock_genera({"sintesi": "S.", "perche_conta": "P."})
    d = assembla_digest(gruppi, genera, data_generazione="2026-07-09")
    sez = d.sezione(Tema.chip)
    assert [g.titolo for g in sez.gruppi] == ["Uno"]
    assert len(genera.prompts) == 1   # solo la sintesi, nessun titolo di gruppo


def test_gruppo_multi_articolo_stesso_giorno_titolo_dal_modello():
    gruppi = {Tema.chip: [_cand(titolo="Uno", url="https://a/1"),
                          _cand(titolo="Due", url="https://a/2")]}

    def genera(prompt):
        genera.prompts.append(prompt)
        if "NOTIZIE:" in prompt:                       # prompt del titolo di gruppo
            return {"titolo": "Riassunto del giorno"}
        return {"sintesi": "S.", "perche_conta": "P."}
    genera.prompts = []

    d = assembla_digest(gruppi, genera, data_generazione="2026-07-09")
    sez = d.sezione(Tema.chip)
    assert len(sez.articoli) == 2
    assert len(sez.gruppi) == 1                          # stesso giorno -> un gruppo
    assert sez.gruppi[0].titolo == "Riassunto del giorno"
    assert len(genera.prompts) == 3                      # 2 sintesi + 1 titolo di gruppo


def test_gruppi_distinti_per_giorni_diversi():
    c_oggi = _cand(titolo="Oggi", url="https://a/1")
    c_ieri = _cand(titolo="Ieri", url="https://a/2")
    c_ieri.data = "2026-07-08"
    genera = _mock_genera({"sintesi": "S.", "perche_conta": "P."})
    d = assembla_digest({Tema.chip: [c_oggi, c_ieri]}, genera, data_generazione="2026-07-09")
    sez = d.sezione(Tema.chip)
    assert {g.data for g in sez.gruppi} == {"2026-07-09", "2026-07-08"}
    # ogni gruppo ha 1 articolo -> nessuna chiamata extra per i titoli
    assert len(genera.prompts) == 2


# --- titolo del gruppo: rifiuti del modello (regressione del 2026-07-21) -----

def _art(titolo="Titolo reale in tema"):
    return Articolo(titolo=titolo, data="2026-07-15", sintesi="s", perche_conta="p")


def test_titolo_gruppo_scarta_il_rifiuto_del_modello():
    # Caso osservato in produzione: il tema data_center del 15/07 mostrava
    # "Nessuna notizia disponibile su data center" come titolo di un gruppo che
    # conteneva 2 articoli. Il ripiego c'era ma copriva solo il titolo vuoto.
    genera = _mock_genera({"titolo": "Nessuna notizia disponibile su data center"})
    titolo = sintetizza_titolo_gruppo(
        Tema.data_center, [_art("Primo articolo vero"), _art("Secondo")], genera
    )
    assert titolo == "Primo articolo vero"


def test_titolo_gruppo_scarta_altre_formule_di_rifiuto():
    for rifiuto in (
        "Non ci sono notizie rilevanti per questo tema",
        "Mi dispiace, non posso generare un titolo",
        "Non e' possibile identificare un filo conduttore",
        "Impossibile determinare un tema comune",
    ):
        genera = _mock_genera({"titolo": rifiuto})
        titolo = sintetizza_titolo_gruppo(
            Tema.chip, [_art("Articolo A"), _art("Articolo B")], genera
        )
        assert titolo == "Articolo A", rifiuto


def test_titolo_gruppo_valido_resta_intatto():
    # Il guardiano non deve diventare un censore: un titolo buono passa,
    # anche se contiene parole che compaiono nelle formule di rifiuto.
    for buono in (
        "NVIDIA avanza nell'AI con nuove infrastrutture",
        "Nessun rallentamento per la domanda di chip AI",
    ):
        genera = _mock_genera({"titolo": buono})
        titolo = sintetizza_titolo_gruppo(
            Tema.chip, [_art("Articolo A"), _art("Articolo B")], genera
        )
        assert titolo == buono
