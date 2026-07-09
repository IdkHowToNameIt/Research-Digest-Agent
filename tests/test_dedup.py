from src.state import SeenStore
from src.tools.fetch import Candidato
from src.tools.dedup import filtra_nuove


def _cand(url):
    return Candidato(titolo="t", url=url, fonte="f", tema="chip", data="", estratto="e")


def test_dedup_persistente(tmp_path):
    db = tmp_path / "seen.sqlite3"
    store = SeenStore(str(db))
    cands = [_cand("https://a.com/1"), _cand("https://a.com/2"), _cand("https://a.com/1")]
    nuove = filtra_nuove(cands, store)
    assert len(nuove) == 2  # il duplicato nella stessa run è escluso

    for c in nuove:
        store.mark_seen(c.url)
    # alla run successiva, niente di nuovo
    assert filtra_nuove(cands, store) == []
    assert store.count() == 2
