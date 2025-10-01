import csv
from pathlib import Path

import pytest

from lothelper.cli import booksrun_sell


@pytest.fixture(autouse=True)
def _booksrun_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOKSRUN_KEY", "test-key")


def test_booksrun_cli_writes_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_path = tmp_path / "books.csv"
    input_path.write_text("isbn\n123\n123\n456\n", encoding="utf-8")
    output_path = tmp_path / "out.csv"

    responses = {
        "123": {
            "isbn": "123",
            "status": "success",
            "http_status": 200,
            "average": 1.0,
            "good": 2.0,
            "new": 3.0,
            "currency": "USD",
            "raw_json": "{}",
        },
        "456": {
            "isbn": "456",
            "status": "success",
            "http_status": 200,
            "average": 4.0,
            "good": 5.0,
            "new": 6.0,
            "currency": "USD",
            "raw_json": "{}",
        },
    }

    seen = []

    def fake_get_sell_quote(isbn: str, session=None):
        seen.append(isbn)
        return responses[isbn]

    monkeypatch.setattr(booksrun_sell.booksrun_client, "get_sell_quote", fake_get_sell_quote)
    monkeypatch.setattr(booksrun_sell.time, "sleep", lambda *_: None)

    exit_code = booksrun_sell.main(
        [
            "--in",
            str(input_path),
            "--out",
            str(output_path),
            "--sleep",
            "0",
            "--format",
            "csv",
        ]
    )

    assert exit_code == 0
    assert seen == ["123", "456"]

    with output_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 2
    assert rows[0]["isbn"] == "123"
    assert set(rows[0].keys()) == set(booksrun_sell.FIELDNAMES)


def test_booksrun_cli_all_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "errors.csv"
    input_path.write_text("isbn\n999\n555\n", encoding="utf-8")
    output_path = tmp_path / "out.csv"

    error_row = {
        "isbn": "",
        "status": "error",
        "http_status": 500,
        "average": None,
        "good": None,
        "new": None,
        "currency": "USD",
        "raw_json": "{}",
    }

    def fake_error(isbn: str, session=None):
        row = error_row.copy()
        row["isbn"] = isbn
        return row

    monkeypatch.setattr(booksrun_sell.booksrun_client, "get_sell_quote", fake_error)
    monkeypatch.setattr(booksrun_sell.time, "sleep", lambda *_: None)

    exit_code = booksrun_sell.main(
        [
            "--in",
            str(input_path),
            "--out",
            str(output_path),
            "--sleep",
            "0",
        ]
    )

    assert exit_code == 1

    with output_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 2
    assert all(row["status"] == "error" for row in rows)

    captured = capsys.readouterr()
    assert "Processed" in captured.out
