"""The single place two commands read the conflict-scoring gateway from the environment.

What reaches the gateway is asserted through `complete()` rather than off the client's
attributes: the model in the posted body is the fact `hivegen-memory-conflict-score` and
`hivegen-pr-conflict-gate` both depend on, and it is what `docs/reference/configuration.md`
documents `CONFLICT_MODEL` as setting.
"""
import pytest

from hivegen import llm as llm_mod
from hivegen.scripts._gateway import gateway_llm

_DEFAULT_MODEL = "minimax/minimax-m3"


@pytest.fixture
def posted(monkeypatch):
    sent = []

    class FakeResp:
        def raise_for_status(self):
            ...

        def json(self):
            return {"choices": [{"message": {"content": "OK"}}]}

    def fake_post(url, **kw):
        sent.append(kw["json"])
        return FakeResp()

    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    return sent


def _configured(monkeypatch, model=None):
    monkeypatch.setenv("BIFROST_BASE", "http://bifrost.invalid/v1")
    monkeypatch.setenv("BIFROST_API_KEY", "k")
    if model is None:
        monkeypatch.delenv("CONFLICT_MODEL", raising=False)
    else:
        monkeypatch.setenv("CONFLICT_MODEL", model)


def test_there_is_no_gateway_without_credentials(monkeypatch):
    monkeypatch.delenv("BIFROST_BASE", raising=False)
    monkeypatch.delenv("BIFROST_API_KEY", raising=False)
    assert gateway_llm() is None


def test_an_unset_conflict_model_scores_with_the_default(monkeypatch, posted):
    _configured(monkeypatch)
    gateway_llm().complete("s", "u")
    assert posted[0]["model"] == _DEFAULT_MODEL


def test_an_empty_conflict_model_scores_with_the_default(monkeypatch, posted):
    """`CONFLICT_MODEL=` is what an unset repository variable exports in the CI this runs in.

    `env: CONFLICT_MODEL: ${{ vars.CONFLICT_MODEL }}` with the variable unset, and
    `export CONFLICT_MODEL="$SOME_UNSET_VAR"` in a wrapper, both set the key to the empty
    string. Empty must mean unset here, the way BIFROST_BASE and BIFROST_API_KEY already
    read it, because the gateway serves no empty model: every request would fail, the
    scorer fail-safes to 1.0 and every memory PR is blocked by a verdict nothing measured.
    """
    _configured(monkeypatch, model="")
    gateway_llm().complete("s", "u")
    assert posted[0]["model"] == _DEFAULT_MODEL


def test_a_conflict_model_that_is_set_is_the_one_asked_for(monkeypatch, posted):
    _configured(monkeypatch, model="vendor/other-m1")
    gateway_llm().complete("s", "u")
    assert posted[0]["model"] == "vendor/other-m1"
