from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Google Gemini
    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Sleeper — league ID pre-wired; override in .env if needed
    sleeper_league_id: str = "1337099185056395264"
    sleeper_user_id: str = "1353482563116630016"   # spuddister
    sleeper_username: str = "spuddister"

    # Reddit (optional — enables player sentiment search)
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "fantasy-ai/0.1"
    reddit_subs: str = "fantasyfootball,dynastyff,DynastyFF,nfl"
    reddit_post_limit: int = 10

    # App
    league_format: str = "dynasty"
    db_path: str = "./data/fantasy.db"

    @property
    def reddit_sub_list(self) -> list[str]:
        return [s.strip() for s in self.reddit_subs.split(",") if s.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
