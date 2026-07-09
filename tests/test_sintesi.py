"""Test di sintesi e assemblaggio (Fase 6). Le chiamate al modello sono mockate.

Basati sui criteri editoriali (sez. 14) e sullo schema (16.6/16.7):
- grounding: metadati reali del candidato, il modello non cambia URL/titolo;
- arXiv: formula di apertura nel prompt + nota preprint aggiunta dal codice (14.8);
- fonti senza estratto: sintesi minima dal titolo (14.6);
- 5 sezioni fisse, il modello non viene invocato per le sezioni vuote (15/16.6).
"""
from src.prompts import APERTURA_ARXIV, NOTA_PREPRINT, prompt_sintesi
from src.schemas import Stato, Tema
from src.sintesi import assembla_digest, sintetizza_candidato
from src.tools.fetch import Candidato


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


def test_prompt_arxiv_include_formula_apertura():
    p = prompt_sintesi(_cand(tema="energia", fonte="arXiv (energia x AI)"))
    assert APERTURA_ARXIV in p


def test_prompt_non_arxiv_senza_formula():
    p = prompt_sintesi(_cand(tema="chip"))
    assert APERTURA_ARXIV not in p


# --- grounding: metadati reali, non del modello -----------------------------

def test_sintetizza_usa_link_reale_ignora_url_del_modello():
    c = _cand(url="https://reale/x")
    genera = _mock_genera({"sintesi": "Testo modello.", "perche_conta": "Conta.",
                           "url": "https://inventato/evil", "titolo": "FAKE"})
    a = sintetizza_candidato(c, genera)
    assert a.fonti[0].link == "https://reale/x"     # link reale del candidato
    assert a.titolo == "Titolo reale"               # titolo reale, non del modello
    assert a.sintesi == "Testo modello."
    assert a.perche_conta == "Conta."


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
