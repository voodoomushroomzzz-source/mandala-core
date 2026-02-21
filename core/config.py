from pydantic import BaseSettings, validator

class Settings(BaseSettings):
    github_token: str
    github_repo: str = "voodoomushroomzzz-source/mandala-core"
    openrouter_key: str = ""
    moonshot_api_key: str = ""
    moonshot_base_url: str = "https://api.moonshot.ai/v1"
    moonshot_model: str = "kimi-k2-turbo-preview"
    log_level: str = "INFO"

    @validator("github_token")
    def token_present(cls, v):
        if not v:
            raise ValueError("GITHUB_TOKEN обязателен")
        return v

    class Config:
        env_file = ".env"

settings = Settings()