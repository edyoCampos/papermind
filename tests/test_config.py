import re
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parent.parent


def test_defaults_sem_localhost():
    s = Settings()
    for v in (s.database_url, s.redis_url, s.ollama_base_url, s.api_url):
        assert "localhost" not in v and "127.0.0.1" not in v


def test_env_prevalece(monkeypatch):
    monkeypatch.setenv("TOP_K", "9")
    assert Settings().top_k == 9


def test_env_example_cobre_settings():
    keys = {l.split("=")[0] for l in (ROOT / ".env.example").read_text().splitlines()
            if re.match(r"^[A-Z_]+=", l)}
    for field in Settings.model_fields:
        assert field.upper() in keys, field
