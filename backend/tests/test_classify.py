"""Test della classificazione sotto-temi e del filtro di rilevanza (Fase 3).

Basati sui criteri di accettazione del Tester, Notion sez. 16.3 (classificazione)
e sez. 13/16.2 (filtro di rilevanza tematica a monte per Google Cloud Blog).
"""
from src.raccolta.classify import classifica, is_rilevante, raggruppa_per_tema
from src.schemas import Tema
from src.raccolta.fetch import Candidato


def _cand(titolo="T", estratto="", tema="chip", filtro=False, url="https://x/1"):
    return Candidato(
        titolo=titolo, url=url, fonte="F", tema=tema, data="2026-07-09",
        estratto=estratto, filtro_rilevanza=filtro,
    )


# --- 16.3 Ogni articolo -> esattamente un tema o None -----------------------

def test_classifica_ritorna_tema_della_fonte():
    assert classifica(_cand(tema="supply_chain")) is Tema.supply_chain


def test_classifica_sempre_tema_singolo_o_none():
    for c in [_cand(tema="chip"), _cand(tema="energia"), _cand(tema="cloud_capacity")]:
        risultato = classifica(c)
        assert risultato is None or isinstance(risultato, Tema)


def test_tema_non_valido_va_a_revisione_manuale():
    assert classifica(_cand(tema="semiconduttori")) is None


# --- 16.2 Filtro di rilevanza a monte (Google Cloud Blog) -------------------

def test_fonte_senza_filtro_sempre_rilevante():
    # una fonte gia' scoped al beat non viene filtrata, anche se il testo e' generico
    c = _cand(titolo="Aggiornamento prodotto", estratto="novita' varie", filtro=False)
    assert is_rilevante(c) is True
    assert classifica(c) is Tema.chip


def test_google_cloud_blog_in_beat_classificato():
    c = _cand(
        titolo="New GPU-to-GPU bandwidth in our data center fabric",
        estratto="3.2 Tbps interconnect for AI clusters",
        tema="cloud_capacity", filtro=True,
    )
    assert is_rilevante(c) is True
    assert classifica(c) is Tema.cloud_capacity


def test_google_cloud_blog_fuori_beat_scartato():
    # contenuto database/sicurezza senza parole del beat -> None (revisione manuale)
    c = _cand(
        titolo="New database features and threat intelligence updates",
        estratto="improved SQL analytics and security posture management",
        tema="cloud_capacity", filtro=True,
    )
    assert is_rilevante(c) is False
    assert classifica(c) is None


# --- Confine di parola (regressione 2026-07-20) ----------------------------
# Prima il confronto era `kw in testo`, cioe' sottostringa pura: bastava una
# parola del beat annidata dentro un'altra per far passare voci fuori beat.
# Casi reali dal feed Tom's Hardware quando e' stato attivato il filtro.

def test_parola_del_beat_dentro_un_altra_parola_non_conta():
    casi = [
        # "mw" dentro "firmware"
        ("Hacker fits 537,000 domains in a $5 ESP32 dongle",
         "custom firmware, 50 KB of RAM, 10 ms response"),
        # "compute" dentro "computer"
        ("Jurassic Park scene recreated on a vintage computer",
         "the original movie prop was a personal computer"),
        # "nm" dentro "nmap"
        ("Weekend project: scanning the home LAN", "a quick nmap sweep"),
    ]
    for titolo, estratto in casi:
        c = _cand(titolo=titolo, estratto=estratto, filtro=True)
        assert is_rilevante(c) is False, titolo


def test_parole_esatte_contano_come_parola_intera():
    # gli stessi termini, ma come parole a se': devono passare
    c = _cand(titolo="New data center draws 300 MW",
              estratto="compute capacity on a 3 nm process", filtro=True)
    assert is_rilevante(c) is True


def test_plurali_e_derivati_passano():
    # il match e' per prefisso ancorato a inizio parola: i plurali non si perdono
    for testo in ["new GPUs shipping", "three new regions", "racks of servers",
                  "chips from the fab", "accelerators for AI"]:
        assert is_rilevante(_cand(titolo=testo, filtro=True)) is True, testo


# --- Fuori beat dal titolo (regressione 2026-07-22) -------------------------
# Il caso reale: l'incidente "modelli OpenAI evadono dal sandbox e hackerano i
# server di HuggingFace" passava il filtro per "servers" e finiva in chip, ma e'
# cronaca di cybersicurezza, non hardware. Se il TITOLO annuncia una storia di
# sicurezza, la voce e' fuori beat anche se il testo tocca parole del beat.

def test_titolo_di_cybersicurezza_scartato_anche_con_parole_beat():
    c = _cand(
        titolo="OpenAI's unreleased AI models break out of testing environment "
               "in unprecedented cybersecurity incident",
        estratto="rogue agents hacked HuggingFace's production servers",
        filtro=True,
    )
    assert is_rilevante(c) is False


def test_attacco_fisico_a_infrastruttura_resta_in_beat():
    # la parola d'esclusione deve stare nel TITOLO: un attacco fisico a un data
    # center e' notizia di beat a pieno titolo e non va persa
    c = _cand(
        titolo="Amazon data center in Bahrain struck and destroyed by cruise missile",
        estratto="the AWS region is offline; capacity rerouted",
        filtro=True,
    )
    assert is_rilevante(c) is True


def test_parola_di_sicurezza_solo_nel_corpo_non_esclude():
    # nel corpo le parole di sicurezza compaiono anche in articoli in beat
    # (es. un roundup): l'esclusione non deve guardare l'estratto
    c = _cand(
        titolo="What's new with Google Cloud: regions and capacity",
        estratto="also this week: a note on ransomware defense",
        filtro=True,
    )
    assert is_rilevante(c) is True


def test_fonte_curata_non_subisce_il_filtro_titolo():
    # una fonte senza filtro_rilevanza titola come vuole (e' gia' scoped al beat)
    c = _cand(titolo="Hardening GPUs against breach attempts", filtro=False)
    assert is_rilevante(c) is True


def test_offerta_commerciale_hardware_viene_scartata():
    # categoria "deals": e' hardware ma non e' notizia di beat
    c = _cand(
        titolo="Save $148 on an AMD Ryzen 7 9800X3D bundle",
        estratto="with 32GB of RAM, motherboard, and liquid cooler",
        filtro=True,
    )
    assert is_rilevante(c) is False


# --- Raggruppamento: 5 chiavi sempre presenti, conteggi coerenti ------------

def test_raggruppa_ha_sempre_cinque_temi():
    gruppi, scartati = raggruppa_per_tema([])
    assert set(gruppi.keys()) == set(Tema)
    assert all(v == [] for v in gruppi.values())
    assert scartati == []


def test_raggruppa_conteggi_e_scartati():
    candidati = [
        _cand(tema="chip", url="https://x/1"),
        _cand(tema="chip", url="https://x/2"),
        _cand(tema="data_center", url="https://x/3"),
        # off-beat da fonte con filtro -> scartato
        _cand(titolo="database security", estratto="sql", tema="cloud_capacity",
              filtro=True, url="https://x/4"),
        # tema non valido -> scartato
        _cand(tema="qualcosa", url="https://x/5"),
    ]
    gruppi, scartati = raggruppa_per_tema(candidati)
    assert len(gruppi[Tema.chip]) == 2
    assert len(gruppi[Tema.data_center]) == 1
    assert len(gruppi[Tema.energia]) == 0
    assert len(scartati) == 2
    # nessun articolo perso: somma raggruppati + scartati == input
    totale = sum(len(v) for v in gruppi.values()) + len(scartati)
    assert totale == len(candidati)


def test_nessun_articolo_in_piu_di_un_tema():
    candidati = [_cand(tema="energia", url=f"https://x/{i}") for i in range(3)]
    gruppi, _ = raggruppa_per_tema(candidati)
    tutti_url = [c.url for v in gruppi.values() for c in v]
    assert len(tutti_url) == len(set(tutti_url))  # nessun duplicato tra i temi
