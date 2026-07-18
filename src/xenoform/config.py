from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class XenoformConfig(BaseSettings):
    cpp_format: str = "file"
    disable_ft: str | None = None
    extmodule_root: Path = Path("./ext")
    # presence-based flag (like disable_ft): any value of XENOFORM_VERBOSE, including empty,
    # enables verbose logging; only absence leaves it off
    verbose: str | None = None

    model_config = SettingsConfigDict(env_prefix="XENOFORM_", extra="ignore")


@cache
def get_config() -> XenoformConfig:
    """Cached config"""
    return XenoformConfig()
