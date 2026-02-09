from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    FRONTEND_URL: str
    NEXT_PUBLIC_FRONTEND_URL: str
    ML_SERVER_URL: str
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    AWS_ACCESS_KEY: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    AWS_BUCKET_NAME: str
    DELETE_S3_AFTER_PROCESSING: bool = True
    ML_SERVER_API_KEY: str
    MAIL: str
    MAIL_PASSWORD: str

    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def settings():
    return Settings()
