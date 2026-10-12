"""bb_mask HTTP istemcisi. Model çağrısı bu modülde yoktur.

complete ailesi henüz açık değil; 501 döner.
doc_id serviste kalır. get_map sözlüğü verir. persist=False state döner.
session() doc_id veya state'i gizler.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8081"
_KURGU0 = "Bu uç henüz açık değil."


class BBError(RuntimeError):
    def __init__(self, status_code: int, detail: str, request_id: str | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.request_id = request_id


@dataclass
class Tagged:
    text: str
    doc_id: str | None = None
    state: dict | None = None
    entities_found: dict = field(default_factory=dict)
    balance_credits: str | None = None
    request_id: str | None = None


class BBAnonym:
    def __init__(self, base_url: str, token: str, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                return client.request(method, f"{self.base_url}{path}", headers=self._headers(), **kwargs)
        except httpx.TimeoutException as exc:
            raise BBError(504, f"Zaman aşımı ({self.timeout} sn). Ücret düşmüş olabilir.") from exc
        except httpx.HTTPError as exc:
            raise BBError(503, f"Servise ulaşılamadı ({self.base_url})") from exc

    def _parse(self, response: httpx.Response) -> dict:
        request_id = response.headers.get("x-request-id")
        if response.status_code >= 400:
            detail = response.text
            try:
                body = response.json()
                if isinstance(body, dict) and body.get("detail"):
                    detail = str(body["detail"])
            except Exception:
                pass
            raise BBError(response.status_code, detail, request_id)
        try:
            body = response.json()
        except ValueError as exc:
            raise BBError(502, "Servis JSON dönmedi", request_id) from exc
        if isinstance(body, dict):
            body["_request_id"] = request_id
        return body

    def _tagged(self, body: dict, persist: bool) -> Tagged:
        doc_id = body.get("doc_id") or None
        if not persist:
            doc_id = None
        return Tagged(
            text=body.get("text") or "",
            doc_id=doc_id,
            state=body.get("state"),
            entities_found=body.get("entities_found") or {},
            balance_credits=body.get("balance_credits"),
            request_id=body.get("_request_id"),
        )

    def anonymize(self, text: str, persist: bool = True) -> Tagged:
        response = self._send("POST", "/v1/anonymize", json={"text": text, "persist": persist})
        return self._tagged(self._parse(response), persist)

    def anonymize_file(self, filename: str, content: bytes, persist: bool = True) -> Tagged:
        response = self._send(
            "POST",
            "/v1/anonymize/file",
            data={"persist": str(persist).lower()},
            files={"file": (filename, content, "application/octet-stream")},
        )
        return self._tagged(self._parse(response), persist)

    def anonymize_path(self, path: str | Path, persist: bool = True) -> Tagged:
        file_path = Path(path)
        return self.anonymize_file(file_path.name, file_path.read_bytes(), persist=persist)

    def anonymize_documents(self, paths: list[str | Path], persist: bool = True) -> Tagged:
        if not 1 <= len(paths) <= 3:
            raise BBError(400, "Bir istekte 1–3 dosya")
        files = []
        for path in paths:
            file_path = Path(path)
            files.append(("files", (file_path.name, file_path.read_bytes(), "application/octet-stream")))
        response = self._send(
            "POST",
            "/v1/anonymize/documents",
            data={"persist": str(persist).lower()},
            files=files,
        )
        return self._tagged(self._parse(response), persist)

    def restore(self, doc_id_or_state: str | dict, model_text: str) -> str:
        payload: dict = {"text": model_text}
        if isinstance(doc_id_or_state, dict):
            payload["state"] = doc_id_or_state
        else:
            payload["doc_id"] = doc_id_or_state
        response = self._send("POST", "/v1/restore", json=payload)
        return self._parse(response).get("text") or ""

    def get_map(self, doc_id: str, once: bool = False) -> dict:
        response = self._send("GET", f"/v1/mappings/{quote(doc_id, safe='')}", params={"once": str(once).lower()})
        return self._parse(response).get("state") or {}

    def delete(self, doc_id: str) -> bool:
        response = self._send("DELETE", f"/v1/mappings/{quote(doc_id, safe='')}")
        return bool(self._parse(response).get("deleted"))

    def complete(self, text: str) -> str:
        raise BBError(501, _KURGU0)

    def complete_file(self, path: str | Path) -> str:
        raise BBError(501, _KURGU0)

    def complete_documents(self, paths: list[str | Path]) -> str:
        raise BBError(501, _KURGU0)


class MaskSession:
    """Kurgu 4. persist=True ise harita bizde kalır ve çıkışta silinir.
    persist=False ise state oturum nesnesindedir."""

    def __init__(self, client: BBAnonym, persist: bool = True):
        self._client = client
        self.persist = persist
        self._ids: list[str] = []
        self._doc_id: str | None = None
        self._state: dict | None = None

    def _remember(self, tagged: Tagged) -> Tagged:
        self._doc_id = tagged.doc_id
        self._state = tagged.state
        if tagged.doc_id:
            self._ids.append(tagged.doc_id)
        return tagged

    def anonymize(self, text: str) -> Tagged:
        return self._remember(self._client.anonymize(text, persist=self.persist))

    def anonymize_file(self, path: str | Path) -> Tagged:
        return self._remember(self._client.anonymize_path(path, persist=self.persist))

    def anonymize_documents(self, paths: list[str | Path]) -> Tagged:
        return self._remember(self._client.anonymize_documents(paths, persist=self.persist))

    def restore(self, model_text: str) -> str:
        if self.persist:
            if not self._doc_id:
                raise BBError(400, "Oturumda anonymize yok")
            return self._client.restore(self._doc_id, model_text)
        if not self._state:
            raise BBError(400, "Oturumda state yok")
        return self._client.restore(self._state, model_text)

    def close(self) -> None:
        if not self.persist:
            self._state = None
            return
        for doc_id in self._ids:
            try:
                self._client.delete(doc_id)
            except BBError:
                pass
        self._ids.clear()


_current: BBAnonym | None = None


def init(api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 120) -> BBAnonym:
    """Süreçte bir kez. Model çağrısı değildir."""
    global _current
    if not api_key.strip():
        raise BBError(401, "api_key boş")
    _current = BBAnonym(base_url, api_key.strip(), timeout)
    return _current


def _require() -> BBAnonym:
    if _current is None:
        raise BBError(401, "bb_mask.init çağrılmadı")
    return _current


def anonymize(text: str, persist: bool = True) -> Tagged:
    return _require().anonymize(text, persist=persist)


def anonymize_file(path: str | Path, persist: bool = True) -> Tagged:
    return _require().anonymize_path(path, persist=persist)


def anonymize_documents(paths: list[str | Path], persist: bool = True) -> Tagged:
    return _require().anonymize_documents(paths, persist=persist)


def restore(doc_id_or_state: str | dict, model_text: str) -> str:
    return _require().restore(doc_id_or_state, model_text)


def get_map(doc_id: str, once: bool = False) -> dict:
    return _require().get_map(doc_id, once=once)


def delete(doc_id: str) -> bool:
    return _require().delete(doc_id)


def complete(text: str) -> str:
    return _require().complete(text)


def complete_file(path: str | Path) -> str:
    return _require().complete_file(path)


def complete_documents(paths: list[str | Path]) -> str:
    return _require().complete_documents(paths)


@contextmanager
def session(persist: bool = True) -> Iterator[MaskSession]:
    handle = MaskSession(_require(), persist=persist)
    try:
        yield handle
    finally:
        handle.close()


async def aanonymize(text: str, persist: bool = True) -> Tagged:
    return await asyncio.to_thread(anonymize, text, persist)


async def aanonymize_file(path: str | Path, persist: bool = True) -> Tagged:
    return await asyncio.to_thread(anonymize_file, path, persist)


async def aanonymize_documents(paths: list[str | Path], persist: bool = True) -> Tagged:
    return await asyncio.to_thread(anonymize_documents, paths, persist)


async def arestore(doc_id_or_state: str | dict, model_text: str) -> str:
    return await asyncio.to_thread(restore, doc_id_or_state, model_text)


async def acomplete(text: str) -> str:
    return await asyncio.to_thread(complete, text)
