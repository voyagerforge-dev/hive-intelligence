import io

from okfgen.load import Doc, is_wave_replen, load_docs


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
