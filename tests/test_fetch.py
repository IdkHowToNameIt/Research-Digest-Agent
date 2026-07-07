from pathlib import Path

from src.tools.fetch import fetch_candidates

# Percorso del feed di esempio risolto rispetto a questo file di test,
# così il test passa indipendentemente dalla cartella da cui lo lanci.
FEED = Path(__file__).resolve().parent.parent / "sample-output" / "sample-feed.xml"


def test_fetch_da_feed_locale():
    cfg = {"fonti": [{"nome": "Esempio", "url": str(FEED), "max": 10}]}
    cands = fetch_candidates(cfg)
    assert len(cands) == 4
    assert all(c.url.startswith("http") for c in cands)
    assert "MCP" in cands[0].titolo or "SDK" in cands[0].titolo
