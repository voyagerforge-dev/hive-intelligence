"""Docling client, document bytes → clean markdown via the Host-A Docling gateway."""
import httpx


class DoclingError(RuntimeError):
    pass


class EmptyConversion(DoclingError):
    """Docling responded 200 OK but produced no md_content, retryable / route-to-fallback."""


class DoclingClient:
    def __init__(self, *, base: str, api_key: str, timeout_s: int = 300, ca_bundle: str = ""):
        self._base = base.rstrip("/")
        self._key = api_key
        self._timeout = timeout_s
        self._verify = ca_bundle or True

    def to_markdown(self, filename: str, content: bytes) -> str:
        """Convert one document to markdown via /v1/convert/file. Born-digital → OCR off;
        tables preserved as markdown."""
        files = {"files": (filename, content)}
        data = {"to_formats": "md", "do_ocr": "false"}
        # Docling on Host-A is LAN-keyless; only send Authorization when a key is set
        # (an empty key would produce a malformed `Bearer ` header that httpx rejects).
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        try:
            r = httpx.post(
                f"{self._base}/v1/convert/file",
                headers=headers,
                files=files, data=data, timeout=self._timeout, verify=self._verify,
            )
        except httpx.HTTPError as e:
            raise DoclingError(f"docling request failed: {e}") from e
        if r.status_code != 200:
            raise DoclingError(f"docling {r.status_code}: {r.text[:200]}")
        md = (r.json().get("document") or {}).get("md_content")
        if not md:
            raise EmptyConversion(f"docling returned empty md_content for {filename}")
        return md
