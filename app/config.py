from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Anthropic API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5-20250929"
    claude_max_tokens: int = 16384
    claude_thinking_budget: int = 8192

    # Upload limits
    max_upload_size_mb: int = 50

    # Paths
    temp_dir: Path = Path("/tmp/rhone-analyzer")
    knowledge_dir: Path = Path(__file__).parent / "knowledge"
    templates_dir: Path = Path(__file__).parent.parent / "templates"

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "rhone-analyzer"

    # Server
    port: int = 8000
    log_level: str = "INFO"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
