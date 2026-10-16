from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_starts_with_empty_database(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CASHBACK_DB_PATH", str(tmp_path / "app.sqlite3"))
    app_path = Path(__file__).resolve().parents[1] / "main.py"
    app = AppTest.from_file(str(app_path), default_timeout=20).run()
    assert not app.exception
    assert any("Your local workspace is empty" in item.value for item in app.info)
