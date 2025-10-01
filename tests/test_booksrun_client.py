import json
from typing import Any, Dict, List

import pytest

from lothelper.vendors import booksrun_client


class DummyResponse:
    def __init__(
        self,
        status_code: int,
        json_payload: Dict[str, Any] | None = None,
        text: str = "",
        json_error: bool = False,
    ) -> None:
        self.status_code = status_code
        self._json_payload = json_payload or {}
        self.text = text
        self._json_error = json_error

    def json(self) -> Dict[str, Any]:
        if self._json_error:
            raise ValueError("invalid json")
        return self._json_payload


class DummySession:
    def __init__(self, responses: List[DummyResponse]) -> None:
        self._responses = responses
        self.calls = 0

    def get(self, *args: Any, **kwargs: Any) -> DummyResponse:
        if not self._responses:
            raise AssertionError("No more responses queued.")
        self.calls += 1
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _booksrun_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOKSRUN_KEY", "test-key")


def test_get_sell_quote_success() -> None:
    data = {
        "result": {
            "status": "success",
            "text": {"Average": "12.5", "Good": 10, "New": 20},
            "currency": "USD",
        }
    }
    session = DummySession([DummyResponse(200, data)])
    quote = booksrun_client.get_sell_quote("1234567890", session=session)

    assert quote == {
        "isbn": "1234567890",
        "status": "success",
        "http_status": 200,
        "average": 12.5,
        "good": 10.0,
        "new": 20.0,
        "currency": "USD",
        "raw_json": json.dumps(data, separators=(",", ":"), sort_keys=True),
    }


def test_get_sell_quote_zero_values() -> None:
    data = {"result": {"status": "success", "text": {"Average": 0, "Good": 0, "New": 0}}}
    session = DummySession([DummyResponse(200, data)])

    quote = booksrun_client.get_sell_quote("0987654321", session=session)

    assert quote["average"] == 0.0
    assert quote["good"] == 0.0
    assert quote["new"] == 0.0
    assert quote["status"] == "success"


def test_get_sell_quote_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        DummyResponse(503, {"result": {"status": "error"}}),
        DummyResponse(429, {"result": {"status": "error"}}),
        DummyResponse(200, {"result": {"status": "success", "text": {"Average": 1}}}),
    ]
    session = DummySession(responses)
    monkeypatch.setattr(booksrun_client.time, "sleep", lambda *_: None)

    quote = booksrun_client.get_sell_quote("111", session=session)

    assert session.calls == 3
    assert quote["status"] == "success"
    assert quote["average"] == 1.0


def test_get_sell_quote_cloudflare_html(monkeypatch: pytest.MonkeyPatch) -> None:
    html = "<!DOCTYPE html><html><body>Blocked</body></html>"
    responses = [
        DummyResponse(503, text=html, json_error=True),
        DummyResponse(503, text=html, json_error=True),
        DummyResponse(503, text=html, json_error=True),
    ]
    session = DummySession(responses)
    monkeypatch.setattr(booksrun_client.time, "sleep", lambda *_: None)

    quote = booksrun_client.get_sell_quote("222", session=session)

    assert quote["status"] == "error"
    assert quote["http_status"] == 503
    assert quote["raw_json"].startswith("<!DOCTYPE html>")
    assert len(quote["raw_json"]) <= 500


def test_get_sell_quote_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOOKSRUN_KEY", raising=False)

    with pytest.raises(booksrun_client.BooksRunConfigurationError):
        booksrun_client.get_sell_quote("333", session=DummySession([]))
