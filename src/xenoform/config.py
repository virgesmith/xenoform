from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class XenoformConfig(BaseSettings):
    cpp_format: str = "file"
    disable_ft: str | None = None
    extmodule_root: Path = Path("./ext")

    model_config = SettingsConfigDict(env_prefix="XENOFORM_", extra="ignore")


@cache
def get_config() -> XenoformConfig:
    """Cached config"""
    return XenoformConfig()
