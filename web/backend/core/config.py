from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # API 기본 설정
    API_PREFIX: str = "/api"
    DEBUG: bool = False

    ALLOWED_ORIGINS: str = ""

    MODEL_SHORT_PATH: str = "artifacts/xgb_short.json"
    MODEL_LONG_PATH: str = "artifacts/xgb_long.json"
    SHORT_HORIZON_DAYS: int = 7
    LONG_HORIZON_MONTHS: int = 6

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v):
        if not v:
            return ""
        if isinstance(v, list):
            return ",".join(v)
        return v

    def allowed_origins_list(self) -> List[str]:
        return [s.strip() for s in self.ALLOWED_ORIGINS.split(",") if s.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"


settings = Settings()