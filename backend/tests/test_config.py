from app.core.config import Settings


def test_settings_reads_exported_gemini_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings()
    assert settings.gemini_api_key == "test-key"
    assert settings.data_dir == tmp_path
