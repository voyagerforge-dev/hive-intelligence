from hivegen.classify_regime import classify_card_regime

CARD = "---\ntitle: DC Order Planning Strategy (OPS)\ndescription: OPS umbrella\ntags: [OPS]\n---\nbody\n"


class Fake:
    def __init__(self, reply): self._reply = reply
    def complete(self, system, user): return self._reply


def test_valid_ops_label():
    out = classify_card_regime(CARD, Fake('{"label":"ops","rationale":"it is the OPS card","confidence":0.9}'))
    assert out["label"] == "ops"
    assert out["confidence"] == 0.9


def test_invalid_label_falls_back_to_none():
    out = classify_card_regime(CARD, Fake('{"label":"banana","confidence":0.5}'))
    assert out["label"] == "none"


def test_garbage_reply_is_none_zero_confidence():
    out = classify_card_regime(CARD, Fake("not json"))
    assert out["label"] == "none" and out["confidence"] == 0.0
