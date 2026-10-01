import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def load_local_env():
    """Load backend/.env for local development without overriding exported values."""
    env_file = Path(__file__).parents[2] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "/tmp/ai-harness")))
    tokens: dict = field(default_factory=lambda: json.loads(os.getenv("AUTH_TOKENS", '{"local-demo-token": ["demo", "default"]}')))
    sandbox_url: str = field(default_factory=lambda: os.getenv("SANDBOX_URL", "http://127.0.0.1:8001"))
    sandbox_token: str = field(default_factory=lambda: os.getenv("SANDBOX_TOKEN", "local-sandbox-token"))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    embedding_model: str = field(default_factory=lambda: os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"))
    image_model: str = field(default_factory=lambda: os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"))
    mongodb_uri: str = field(default_factory=lambda: os.getenv("MONGODB_URI", ""))
    mongodb_database: str = field(default_factory=lambda: os.getenv("MONGODB_DATABASE", "chatbot_harness"))
    persistence_mode: str = field(default_factory=lambda: os.getenv("PERSISTENCE_MODE", "auto"))
    r2_bucket: str = field(default_factory=lambda: os.getenv("R2_BUCKET", ""))
    r2_endpoint_url: str = field(default_factory=lambda: os.getenv("R2_ENDPOINT_URL", ""))
    r2_access_key_id: str = field(default_factory=lambda: os.getenv("R2_ACCESS_KEY_ID", ""))
    r2_secret_access_key: str = field(default_factory=lambda: os.getenv("R2_SECRET_ACCESS_KEY", ""))
    max_attempts: int = 3
    max_steps: int = 8
    workspace_max_steps: int = field(default_factory=lambda: int(os.getenv("WORKSPACE_MAX_STEPS", "80")))
    workspace_max_batches: int = field(default_factory=lambda: int(os.getenv("WORKSPACE_MAX_BATCHES", "0")))
    max_upload_bytes: int = 500_000
