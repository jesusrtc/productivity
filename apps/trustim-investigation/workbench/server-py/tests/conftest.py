"""Shared test fixtures for the Juniper FastAPI server."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _isolate_dirs(tmp_path):
    """Redirect all data dirs to a temp directory so tests don't touch real data."""
    orig = {
        "sessions_dir": settings.sessions_dir,
        "alerts_dir": settings.alerts_dir,
        "automations_dir": settings.automations_dir,
        "playbooks_dir": settings.playbooks_dir,
        "templates_dir": settings.templates_dir,
        "notebooks_dir": settings.notebooks_dir,
        "ioc_db_path": settings.ioc_db_path,
    }
    settings.sessions_dir = tmp_path / "sessions"
    settings.alerts_dir = tmp_path / "alerts"
    settings.automations_dir = tmp_path / "automations"
    settings.playbooks_dir = tmp_path / "playbooks"
    settings.templates_dir = tmp_path / "templates"
    settings.notebooks_dir = tmp_path / "notebooks"
    settings.ioc_db_path = tmp_path / "ioc-db.json"

    # Ensure dirs exist (lifespan normally does this)
    for d in [
        settings.sessions_dir,
        settings.alerts_dir,
        settings.automations_dir,
        settings.playbooks_dir,
        settings.templates_dir,
        settings.notebooks_dir,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    yield

    # Restore
    for k, v in orig.items():
        setattr(settings, k, v)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
