from hiveserve.config import Settings
from hiveserve.identity import resolve_owner


def test_header_present():
    s = Settings()
    assert resolve_owner({"x-forwarded-email": "alice@co"}, s) == "alice@co"


def test_header_case_insensitive():
    s = Settings()
    assert resolve_owner({"X-Forwarded-Email": "bob@co"}, s) == "bob@co"


def test_missing_falls_back_to_default():
    s = Settings()
    assert resolve_owner({}, s) == s.okf_default_owner
    assert resolve_owner(None, s) == s.okf_default_owner
    assert resolve_owner({"x-forwarded-email": ""}, s) == s.okf_default_owner


def test_starlette_headers_object():
    from starlette.datastructures import Headers
    s = Settings()
    h = Headers({"X-Forwarded-Email": "carol@co"})
    assert resolve_owner(h, s) == "carol@co"
