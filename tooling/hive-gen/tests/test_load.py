"""Slicing a corpus into generatable areas.

These tests use a **synthetic corpus profile** written into ``tmp_path``, not a real one.
That is the point of the profile: the areas, sub-areas and topics are one corpus's
vocabulary, and what the product owns is the slicing mechanism. Testing against a real
vocabulary would assert that a particular YAML file exists, which is not a property of the
software.
"""
import io
import textwrap

import pytest

from hivegen.load import Doc, load_area_local, load_docs, load_docs_local, load_subarea_local
from hivegen.profile import load_profile

PROFILE = textwrap.dedent("""
    areas:
      intake: [Receiving, Putaway]
      dispatch: [Outbound]
    subareas:
      link-alpha:
        topics: [Links]
        include: [alpha]
      link-beta:
        topics: [Links]
        include: [beta]
        exclude: [legacy]
      link-rest:
        topics: [Links]
        exclude: [alpha, beta]
    guide_topics:
      "Guide: Intake": "Everything about receiving goods."
    retopic_bucket: "generic reference"
    products:
      widgets: WIDGETS
""").strip()


@pytest.fixture
def profile(tmp_path):
    (tmp_path / "corpus-profile.yaml").write_text(PROFILE)
    return load_profile(explicit=str(tmp_path / "corpus-profile.yaml"))


def _doc(topic: str, body: str = "body") -> str:
    return f"---\ntitle: T\nslug: s\ntopic: {topic}\n---\n\n{body}\n"


# --------------------------------------------------------------------------
# The profile itself
# --------------------------------------------------------------------------


def test_profile_loads_every_section(profile):
    assert profile.areas["intake"] == ("Receiving", "Putaway")
    assert profile.subareas["link-beta"].exclude == ("legacy",)
    assert profile.guide_topics == {"Guide: Intake": "Everything about receiving goods."}
    assert profile.retopic_bucket == "generic reference"
    assert profile.products == {"widgets": "WIDGETS"}
    assert not profile.is_empty


def test_absent_profile_is_empty_rather_than_an_error(tmp_path):
    """Import time must not depend on a corpus being present. The error belongs at the
    point something asks for a vocabulary that does not exist."""
    p = load_profile(explicit=str(tmp_path / "nope.yaml"), atomic_dir=str(tmp_path))
    assert p.is_empty
    assert p.areas == {}


def test_subarea_without_topics_is_rejected(tmp_path):
    """A sub-area naming no topics matches nothing, silently. A slice that loads zero
    documents is indistinguishable from a corpus that has none, so refuse it up front."""
    f = tmp_path / "corpus-profile.yaml"
    f.write_text("subareas:\n  broken:\n    include: [x]\n")
    with pytest.raises(ValueError, match="at least one topic"):
        load_profile(explicit=str(f))


def test_non_mapping_profile_is_rejected(tmp_path):
    f = tmp_path / "corpus-profile.yaml"
    f.write_text("- just\n- a\n- list\n")
    with pytest.raises(TypeError, match="must be a mapping"):
        load_profile(explicit=str(f))


# --------------------------------------------------------------------------
# Slicing
# --------------------------------------------------------------------------


def test_load_area_selects_by_topic(tmp_path, profile):
    d = tmp_path / "atomic"; d.mkdir()
    (d / "a.md").write_text(_doc("Putaway"))
    (d / "b.md").write_text(_doc("Outbound"))
    assert [x.name for x in load_area_local(d, "intake", profile)] == ["a.md"]


def test_unknown_area_names_what_the_profile_defines(tmp_path, profile):
    d = tmp_path / "atomic"; d.mkdir()
    with pytest.raises(KeyError) as e:
        load_area_local(d, "not-an-area", profile)
    assert "intake" in str(e.value) and "dispatch" in str(e.value)


def test_unknown_area_without_a_profile_says_so(tmp_path):
    """The failure mode this replaces: 'unknown area X' when the real problem is that no
    vocabulary was loaded at all."""
    d = tmp_path / "atomic"; d.mkdir()
    empty = load_profile(explicit=str(tmp_path / "nope.yaml"), atomic_dir=str(tmp_path))
    with pytest.raises(KeyError) as e:
        load_area_local(d, "intake", empty)
    assert "no corpus profile found" in str(e.value)
    assert "CORPUS_PROFILE" in str(e.value)


def test_subarea_narrows_a_topic_by_filename(tmp_path, profile):
    d = tmp_path / "atomic"; d.mkdir()
    (d / "link-alpha-one.md").write_text(_doc("Links"))
    (d / "link-beta-two.md").write_text(_doc("Links"))
    (d / "link-beta-legacy.md").write_text(_doc("Links"))
    (d / "link-gamma.md").write_text(_doc("Links"))

    assert [x.name for x in load_subarea_local(d, "link-alpha", profile)] == ["link-alpha-one.md"]
    # exclude subtracts from include
    assert [x.name for x in load_subarea_local(d, "link-beta", profile)] == ["link-beta-two.md"]
    # the remainder slice sweeps what the named families did not claim
    assert [x.name for x in load_subarea_local(d, "link-rest", profile)] == ["link-gamma.md"]


def test_subareas_sharing_a_topic_stay_disjoint(tmp_path, profile):
    """The property that makes sub-slicing safe: no document lands in two slices that draw
    from the same topic, so no document is distilled twice."""
    d = tmp_path / "atomic"; d.mkdir()
    for n in ("link-alpha-one", "link-beta-two", "link-gamma"):
        (d / f"{n}.md").write_text(_doc("Links"))

    seen: list[str] = []
    for name in ("link-alpha", "link-beta", "link-rest"):
        seen += [x.name for x in load_subarea_local(d, name, profile)]
    assert len(seen) == len(set(seen)) == 3


def test_load_docs_local_with_no_filters_returns_everything(tmp_path):
    d = tmp_path / "atomic"; d.mkdir()
    (d / "a.md").write_text("a")
    (d / "b.md").write_text("b")
    (d / "notes.txt").write_text("ignored")
    assert sorted(x.name for x in load_docs_local(d)) == ["a.md", "b.md"]


def test_frontmatter_topic_parses_and_degrades(tmp_path):
    from hivegen.load import frontmatter_topic
    assert frontmatter_topic(_doc("Receiving")) == "Receiving"
    assert frontmatter_topic("no frontmatter here") == ""
    assert frontmatter_topic("---\n: : broken\n---\nbody") == ""


# --------------------------------------------------------------------------
# Object storage
# --------------------------------------------------------------------------


class FakeS3:
    def __init__(self, objs: dict[str, str]):
        self._objs = objs

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": k} for k in self._objs if k.startswith(Prefix)]}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self._objs[Key].encode())}


def test_load_docs_reads_markdown_only():
    s3 = FakeS3({"p/docs/a.md": "body", "p/_manifest.jsonl": "{}"})
    docs = load_docs(s3, "b", "p/")
    assert [d.name for d in docs] == ["p/docs/a.md"]
    assert docs[0].text == "body"
    assert isinstance(docs[0], Doc)


def test_load_docs_can_narrow_by_filename_keyword():
    s3 = FakeS3({"p/alpha-one.md": "a", "p/beta-two.md": "b"})
    docs = load_docs(s3, "b", "p/", name_keywords=["alpha"])
    assert [d.name for d in docs] == ["p/alpha-one.md"]
