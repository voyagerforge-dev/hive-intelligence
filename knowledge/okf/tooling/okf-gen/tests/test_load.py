import io

from okfgen.load import Doc, is_wave_replen, load_docs, load_docs_local


def test_is_wave_replen_matches_and_rejects():
    assert is_wave_replen("example_prefix/docs/wave-template-picking-parameters.md")
    assert is_wave_replen("example_prefix/docs/activity-tracking-inquiry-fs-300-replenishment.md")
    assert is_wave_replen("example_prefix/docs/shipping-wave-major-minor.md")
    assert not is_wave_replen("example_prefix/docs/fedex-express.md")


class FakeS3:
    def __init__(self, objs: dict[str, str]):
        self._objs = objs

    def list_objects_v2(self, Bucket, Prefix):
        keys = [k for k in self._objs if k.startswith(Prefix)]
        return {"Contents": [{"Key": k} for k in keys]}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self._objs[Key].encode())}


def test_load_docs_filters_to_wave_replen():
    s3 = FakeS3({
        "example_prefix/docs/wave-template.md": "wave body",
        "example_prefix/docs/fedex-express.md": "carrier body",
        "example_prefix/_manifest.jsonl": "{}",
    })
    docs = load_docs(s3, "b", "example_prefix/")
    assert [d.name for d in docs] == ["example_prefix/docs/wave-template.md"]
    assert docs[0].text == "wave body"
    assert isinstance(docs[0], Doc)


def test_load_docs_local_filters_and_reads(tmp_path):
    d = tmp_path / "atomic"
    d.mkdir()
    (d / "shipping-wave-major-minor-order-fs.md").write_text("wave body")
    (d / "lean-time-replenishment-fs.md").write_text("replen body")
    (d / "fedex-express-carrier.md").write_text("carrier body")
    (d / "notes.txt").write_text("ignore me")
    docs = load_docs_local(d)
    names = sorted(x.name for x in docs)
    assert names == ["lean-time-replenishment-fs.md", "shipping-wave-major-minor-order-fs.md"]
    by_name = {x.name: x for x in docs}
    assert by_name["shipping-wave-major-minor-order-fs.md"].text == "wave body"
    assert isinstance(docs[0], Doc)


def test_load_docs_local_no_filter_includes_all_md(tmp_path):
    d = tmp_path / "atomic"
    d.mkdir()
    (d / "wave.md").write_text("a")
    (d / "fedex.md").write_text("b")
    docs = load_docs_local(d, only_wave_replen=False)
    assert sorted(x.name for x in docs) == ["fedex.md", "wave.md"]
