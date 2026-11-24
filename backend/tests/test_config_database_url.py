"""PostgreSQL URLs are read with the installed psycopg (v3) driver, whatever prefix the .env uses."""

import pytest

from app.core.config import Settings


@pytest.mark.parametrize("url", [
    "postgresql://u:p@localhost:5432/carecircle",
    "postgres://u:p@localhost:5432/carecircle",
    "postgresql+psycopg2://u:p@localhost:5432/carecircle",
    "postgresql+psycopg://u:p@localhost:5432/carecircle",
])
def test_postgres_urls_use_psycopg(url):
    assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@localhost:5432/carecircle"


def test_sqlite_url_is_unchanged():
    assert Settings(database_url="sqlite:///./x.db").database_url == "sqlite:///./x.db"
