import httpx
import pytest
import respx

from hiveprep.docling_client import DoclingClient, DoclingError, EmptyConversion

BASE = "http://docling.test"


def _client():
    return DoclingClient(base=BASE, api_key="k", timeout_s=5)


@respx.mock
def test_to_markdown_ok():
    respx.post(f"{BASE}/v1/convert/file").mock(
        return_value=httpx.Response(200, json={"document": {"md_content": "# Hi\n\n| a | b |"}}))
    assert "| a | b |" in _client().to_markdown("d.pdf", b"%PDF-...")


@respx.mock
def test_empty_conversion_raises():
    respx.post(f"{BASE}/v1/convert/file").mock(
        return_value=httpx.Response(200, json={"document": {"md_content": ""}}))
    with pytest.raises(EmptyConversion):
        _client().to_markdown("d.pdf", b"%PDF-")


@respx.mock
def test_non_200_raises_docling_error():
    respx.post(f"{BASE}/v1/convert/file").mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(DoclingError):
        _client().to_markdown("d.pdf", b"%PDF-")
