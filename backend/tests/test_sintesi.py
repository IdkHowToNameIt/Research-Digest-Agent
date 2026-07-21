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
    _frammento_da_titolo,
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


def _mock_sequenza(*risposte):
    """Generatore finto che risponde diversamente a ogni chiamata."""
    def genera(prompt):
        genera.prompts.append(prompt)
        return dict(risposte[min(len(genera.prompts) - 1, len(risposte) - 1)])
    genera.prompts = []
    return genera


def test_su_rifiuto_compone_il_titolo_dalle_etichette():
    # Caso osservato in produzione (data_center del 15/07): il modello rifiuta il
    # titolo-sommario perche' le notizie non hanno un filo comune. Invece di
    # ripiegare sul titolo del PRIMO articolo, nascondendo il secondo, si chiede
    # un'etichetta per notizia e si accostano.
    genera = _mock_sequenza(
        {"titolo": "Nessuna notizia disponibile su data center"},
        {"etichette": ["Ottimizzazione annunci Meta", "Progressi nel fine-tuning"]},
    )
    titolo = sintetizza_titolo_gruppo(
        Tema.data_center, [_art("Primo"), _art("Secondo")], genera
    )
    assert titolo == "Ottimizzazione annunci Meta; progressi nel fine-tuning"
    assert len(genera.prompts) == 2          # e' servita una seconda chiamata
    assert "etichetta" in genera.prompts[1].lower()


def test_titolo_composto_si_ferma_a_due_frammenti_e_segnala_il_resto():
    # Con 4 articoli la riga resterebbe illeggibile: max 2 frammenti + "e altro".
    genera = _mock_sequenza(
        {"titolo": "Non ci sono notizie collegate"},
        {"etichette": ["Liquid cooling", "Nuove regole USA", "Terza", "Quarta"]},
    )
    titolo = sintetizza_titolo_gruppo(
        Tema.data_center, [_art("A"), _art("B"), _art("C"), _art("D")], genera
    )
    assert titolo == "Liquid cooling; nuove regole USA e altro"


def test_se_anche_le_etichette_falliscono_si_usano_i_titoli_reali():
    # Il modello che ha appena rifiutato puo' rifiutare di nuovo: il ripiego
    # deterministico non costa quota e non lascia il caso scoperto.
    genera = _mock_sequenza(
        {"titolo": "Nessuna notizia disponibile"},
        {"etichette": ["Non e' possibile determinare un tema"]},
    )
    titolo = sintetizza_titolo_gruppo(
        Tema.chip,
        [_art("NVIDIA amplia la produzione per il mercato cinese"),
         _art("TSMC investe in Arizona dopo gli utili record")],
        genera,
    )
    assert titolo == "NVIDIA amplia la produzione; TSMC investe in Arizona"


def test_se_la_seconda_chiamata_esplode_si_ripiega_lo_stesso():
    def genera(prompt):
        genera.n += 1
        if genera.n == 1:
            return {"titolo": "Nessuna notizia disponibile"}
        raise RuntimeError("modello KO")
    genera.n = 0
    titolo = sintetizza_titolo_gruppo(
        Tema.chip, [_art("Primo titolo vero"), _art("Secondo titolo vero")], genera
    )
    assert titolo == "Primo titolo vero; secondo titolo vero"


def test_frammento_non_finisce_su_articolo_o_preposizione():
    # Tagliando a lunghezza fissa si finisce spesso su "la"/"degli", che fa
    # sembrare la riga troncata a meta'. Verificato su titoli reali del run.
    for t in (
        "Bristol Myers Squibb costruisce la fabbrica AI piu' avanzata",
        "Esplorazione della rappresentazione gerarchica degli interessi Meta",
        "Nemotron Labs: Come i Modelli Aperti Offrono alle Imprese",
    ):
        assert not _frammento_da_titolo(t).split()[-1].lower().rstrip("'") in {
            "la", "degli", "i", "e", "di", "dell",
        }


def test_titolo_coerente_non_scatena_la_seconda_chiamata():
    # Il costo aggiuntivo deve restare confinato ai gruppi problematici.
    genera = _mock_sequenza({"titolo": "NVIDIA avanza nell'AI con nuove infrastrutture"})
    titolo = sintetizza_titolo_gruppo(Tema.chip, [_art("A"), _art("B")], genera)
    assert titolo == "NVIDIA avanza nell'AI con nuove infrastrutture"
    assert len(genera.prompts) == 1


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


def test_le_sigle_non_vengono_minuscolizzate():
    # "tSMC" era il risultato della versione ingenua che abbassava sempre
    # l'iniziale del secondo frammento.
    genera = _mock_sequenza(
        {"titolo": "Nessuna notizia disponibile"},
        {"etichette": ["Domanda di chip", "TSMC investe in Arizona"]},
    )
    assert sintetizza_titolo_gruppo(
        Tema.chip, [_art("A"), _art("B")], genera
    ) == "Domanda di chip; TSMC investe in Arizona"


def test_etichette_troppo_lunghe_vengono_accorciate():
    # Il prompt chiede 2-5 parole ma non puo' imporlo. Se il modello rimanda i
    # titoli interi (successo in una riprova sui gruppi reali del run) la riga
    # composta diventerebbe illeggibile sulla card.
    lunga = ("Esplorazione della rappresentazione gerarchica degli interessi "
             "per l'ottimizzazione degli annunci Meta")
    genera = _mock_sequenza(
        {"titolo": "Nessuna notizia disponibile"},
        {"etichette": [lunga, "Progressi nel fine-tuning riducono il volume totale"]},
    )
    titolo = sintetizza_titolo_gruppo(Tema.data_center, [_art("A"), _art("B")], genera)
    # Senza il tetto la riga sarebbe di 168 caratteri: 82 misurati con il cap.
    assert len(titolo) <= 90, titolo
    assert titolo.startswith("Esplorazione della rappresentazione gerarchica")
    assert "annunci Meta" not in titolo          # la coda lunga e' stata tagliata
