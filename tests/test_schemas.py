from src.schemas import Digest, DigestItem


def test_digest_valido():
    item = DigestItem(
        titolo="Titolo", fonte="Fonte", url="https://example.com/x",
        sintesi="Sintesi breve.", perche_conta="Conta perché.", tag=["a"],
    )
    d = Digest(beat="Test", generato_il="2026-06-19T00:00:00Z", voci=[item])
    assert d.voci[0].url == "https://example.com/x"
    assert d.model_dump()["voci"][0]["titolo"] == "Titolo"
