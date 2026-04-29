import time

from pydantic_settings import BaseSettings
from pathlib import Path

start_time: float = time.time()


class Settings(BaseSettings):
    repo_root: Path = Path(__file__).resolve().parents[3]  # trustim-investigation/
    sessions_dir: Path = Path(__file__).resolve().parents[2] / ".sessions"
    skills_dir: Path = Path(__file__).resolve().parents[3] / "skills"
    alerts_dir: Path = Path(__file__).resolve().parents[2] / ".alerts"
    automations_dir: Path = Path(__file__).resolve().parents[2] / ".automations"
    playbooks_dir: Path = Path(__file__).resolve().parents[2] / ".playbooks"
    templates_dir: Path = Path(__file__).resolve().parents[2] / ".templates"
    notebooks_dir: Path = Path(__file__).resolve().parents[2] / "notebooks"
    ioc_db_path: Path = Path(__file__).resolve().parents[2] / ".ioc-db.json"
    port: int = 3200
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
    ]


settings = Settings()
