"""YAML/CSV config loader — singleton accessors for business knowledge."""

from __future__ import annotations

import csv
import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


def _root_candidates() -> list[Path]:
    roots: list[Path] = []
    here = Path(__file__).resolve()
    roots.extend(here.parents[i] for i in range(min(6, len(here.parents))))
    roots.append(Path.cwd())
    for key in ("LAMBDA_TASK_ROOT", "VERCEL_FUNC_DIR", "HARBORMASTER_ROOT"):
        raw = os.environ.get(key)
        if raw:
            roots.append(Path(raw))
    out: list[Path] = []
    seen: set[str] = set()
    for path in roots:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            out.append(resolved)
    return out


def _repo_root() -> Path:
    for path in _root_candidates():
        if (path / "config" / "thresholds.yaml").is_file():
            return path
        if (path / "web" / "index.html").is_file():
            return path
    return Path(__file__).resolve().parents[2]


def is_serverless() -> bool:
    return bool(
        os.environ.get("VERCEL")
        or os.environ.get("VERCEL_ENV")
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    )


def _tmp_data() -> Path:
    return Path(os.environ.get("TMPDIR") or "/tmp") / "harbormaster"


def _can_mkdir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".hm_write"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def apply_vercel_env() -> None:
    """Writable scratch dir on Vercel. Ledger uses Postgres when DATABASE_URL is set."""
    if not is_serverless():
        return
    if os.environ.get("HARBORMASTER_VERCEL_READY") == "1":
        return
    tmp = _tmp_data()
    inbox = tmp / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    src_inbox = _repo_root() / "data" / "inbox"
    if src_inbox.is_dir():
        for path in src_inbox.glob("demo_*.json"):
            dest = inbox / path.name
            if not dest.exists():
                shutil.copy2(path, dest)
    os.environ["DATA_DIR"] = str(tmp)
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        os.environ["DB_PATH"] = str(tmp / "harbormaster.db")
    os.environ.setdefault("HARBORMASTER_ENV", "prod")
    if os.environ.get("INBOX_BASE_URL", "http://localhost:8080") in {
        "",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    }:
        os.environ["INBOX_BASE_URL"] = ""
    os.environ["HARBORMASTER_VERCEL_READY"] = "1"
    cached = globals().get("get_settings")
    if cached is not None:
        cached.cache_clear()


class Settings(BaseSettings):
    """All runtime knobs come from the environment — nothing is hardcoded."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    inbox_base_url: str = "http://localhost:8080"
    database_url: str | None = None
    db_path: str | None = None
    data_dir: str | None = None
    config_dir: str | None = None
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "deepseek-ai/DeepSeek-V4-Flash-0731"
    openai_models: str = "deepseek-ai/DeepSeek-V4-Flash-0731,MiniMaxAI/MiniMax-M2.7,zai-org/GLM-5.3-Flash"
    vision_model: str = "zai-org/GLM-5.3-Flash"
    log_level: str = "INFO"
    llm_timeout_s: float = 60.0
    inbox_timeout_s: float = 30.0
    pipeline_concurrency: int = 4
    cache_extractions: bool = True
    harbormaster_env: str = "dev"
    cors_origins: str = "*"
    api_key: str = ""
    rate_limit_per_min: int = 120
    rate_limit_heavy_per_min: int = 8
    max_body_bytes: int = 12_000_000
    # Object storage — empty bucket keeps files on local disk (data/objects).
    s3_bucket: str = ""
    s3_endpoint: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_prefix: str = "harbormaster/"
    s3_force_path_style: bool = True
    backup_interval_hours: float = 0
    worker_threads: int = 2
    sdoc_bundle_dir: str = ""

    @property
    def model_fallbacks(self) -> list[str]:
        raw = os.getenv("OPENAI_MODELS") or self.openai_models
        names = [self.openai_model]
        for part in raw.split(","):
            name = part.strip()
            if name and name not in names:
                names.append(name)
        return names

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (os.getenv("CORS_ORIGINS") or self.cors_origins or "*").strip()
        if raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def service_api_key(self) -> str:
        return (os.getenv("HARBORMASTER_API_KEY") or self.api_key or "").strip()

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def s3_configured(self) -> bool:
        return bool((os.getenv("S3_BUCKET") or self.s3_bucket or "").strip())

    @property
    def object_prefix(self) -> str:
        raw = (os.getenv("S3_PREFIX") or self.s3_prefix or "harbormaster/").strip()
        return raw if raw.endswith("/") else raw + "/"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


if is_serverless():
    apply_vercel_env()


def config_dir() -> Path:
    override = os.getenv("CONFIG_DIR") or get_settings().config_dir
    if override:
        return Path(override)
    return _repo_root() / "config"


def data_dir() -> Path:
    override = os.getenv("DATA_DIR") or get_settings().data_dir
    if override:
        path = Path(override)
        path = path if path.is_absolute() else _repo_root() / path
    else:
        path = _repo_root() / "data"
    if is_serverless() and not _can_mkdir(path):
        path = _tmp_data()
        path.mkdir(parents=True, exist_ok=True)
        return path
    path.mkdir(parents=True, exist_ok=True)
    return path


def web_dir() -> Path:
    for root in _root_candidates():
        candidate = root / "web"
        if (candidate / "index.html").is_file():
            return candidate
        public = root / "public"
        if (public / "index.html").is_file():
            return public
    return _repo_root() / "web"


def bundle_dir() -> Path | None:
    """Official SDOC inbox (520 emails + attachments)."""
    settings = get_settings()
    candidates = [
        os.getenv("SDOC_BUNDLE_DIR") or settings.sdoc_bundle_dir,
        r"D:\Downloads\sdoc-hackathon-bundle",
        str(_repo_root() / "sdoc-hackathon-bundle"),
        str(data_dir() / "sdoc"),
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = _repo_root() / path
        if (path / "inbox").is_dir() and any((path / "inbox").glob("email_*.json")):
            return path
    return None


def cache_dir() -> Path:
    path = data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    settings = get_settings()
    url = os.getenv("DATABASE_URL") or settings.database_url
    path: Path | None = None
    if url:
        parsed = urlparse(url)
        if parsed.scheme.startswith("sqlite"):
            raw = parsed.path or ""
            if parsed.netloc and parsed.netloc not in {".", ""}:
                raw = f"{parsed.netloc}{raw}"
            raw = raw.lstrip("/")
            if raw:
                candidate = Path(raw)
                path = candidate if candidate.is_absolute() else _repo_root() / candidate
    if path is None:
        override = os.getenv("DB_PATH") or settings.db_path
        if override:
            candidate = Path(override)
            path = candidate if candidate.is_absolute() else _repo_root() / candidate
        else:
            path = data_dir() / "harbormaster.db"
    url = os.getenv("DATABASE_URL") or settings.database_url or ""
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        return Path("<postgres>")
    if path is None:
        path = data_dir() / "harbormaster.db"
    if is_serverless() and not _can_mkdir(path.parent):
        path = _tmp_data() / "harbormaster.db"
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_yaml(name: str) -> dict[str, Any]:
    path = config_dir() / name
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{name} must be a mapping")
    return data


def load_prompt(name: str) -> str:
    path = config_dir() / "prompts" / name
    return path.read_text(encoding="utf-8")


class FieldRisk(BaseModel):
    risk_level: str = "low"
    exposure_usd: float = 5000.0
    advise: str = "PILOT — unpriced field"
    weight: float = 0.3


class RiskMatrix(BaseModel):
    fields: dict[str, FieldRisk] = Field(default_factory=dict)
    defaults: dict[str, FieldRisk] = Field(default_factory=dict)

    def for_field(self, name: str) -> FieldRisk:
        if name in self.fields:
            return self.fields[name]
        if name == "gross_weight_kg" and "gross_weight" in self.fields:
            return self.fields["gross_weight"]
        if name == "gross_weight" and "gross_weight_kg" in self.fields:
            return self.fields["gross_weight_kg"]
        return self.defaults.get("unknown_field", FieldRisk())


class Thresholds(BaseModel):
    extract_min_confidence: float = 0.75
    match_confidence_floor: float = 0.92
    uncertain_band: float = 0.08
    fuzzy_match_threshold: float = 0.92
    scout_rule_confidence: float = 0.95
    scout_llm_min_confidence: float = 0.70
    scout_unknown_below: float = 0.55
    unreadable_min_chars: int = 40
    presets: dict[str, dict[str, float]] = Field(default_factory=dict)

    def apply_preset(self, name: str) -> Thresholds:
        preset = self.presets.get(name)
        if not preset:
            return self
        return self.model_copy(update=preset)


class EntitySuffixConfig(BaseModel):
    suffixes: list[str] = Field(default_factory=list)
    strip_chars: str = ".,\"'()/"
    normalize_ampersand: bool = True
    collapse_whitespace: bool = True


class LocodeRow(BaseModel):
    locode: str
    name: str
    country: str = ""
    aliases: list[str] = Field(default_factory=list)


@lru_cache(maxsize=1)
def get_risk_matrix() -> RiskMatrix:
    raw = _load_yaml("risk_matrix.yaml")
    fields = {k: FieldRisk(**v) for k, v in (raw.get("fields") or {}).items()}
    defaults = {k: FieldRisk(**v) for k, v in (raw.get("defaults") or {}).items()}
    return RiskMatrix(fields=fields, defaults=defaults)


@lru_cache(maxsize=1)
def get_thresholds() -> Thresholds:
    raw = _load_yaml("thresholds.yaml")
    return Thresholds(**raw)


@lru_cache(maxsize=1)
def get_field_aliases() -> dict[str, list[str]]:
    raw = _load_yaml("field_aliases.yaml")
    return {k: list(v) for k, v in raw.items()}


@lru_cache(maxsize=1)
def get_entity_suffixes() -> EntitySuffixConfig:
    raw = _load_yaml("entity_suffixes.yaml")
    return EntitySuffixConfig(**raw)


@lru_cache(maxsize=1)
def get_locodes() -> list[LocodeRow]:
    path = config_dir() / "locodes.csv"
    rows: list[LocodeRow] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            aliases = [a.strip() for a in (r.get("aliases") or "").split("|") if a.strip()]
            rows.append(
                LocodeRow(
                    locode=r["locode"].strip(),
                    name=r["name"].strip(),
                    country=(r.get("country") or "").strip(),
                    aliases=aliases,
                )
            )
    return rows


def clear_caches() -> None:
    get_settings.cache_clear()
    get_risk_matrix.cache_clear()
    get_thresholds.cache_clear()
    get_field_aliases.cache_clear()
    get_entity_suffixes.cache_clear()
    get_locodes.cache_clear()


# Mutable runtime autonomy override (API dial)
_runtime_thresholds: Thresholds | None = None


def runtime_thresholds() -> Thresholds:
    global _runtime_thresholds
    if _runtime_thresholds is None:
        _runtime_thresholds = get_thresholds()
    return _runtime_thresholds


def set_runtime_thresholds(t: Thresholds) -> None:
    global _runtime_thresholds
    _runtime_thresholds = t
