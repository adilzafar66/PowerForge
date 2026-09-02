"""Live database checks. Skipped unless RUN_INTEGRATION=1 and PostgreSQL is reachable."""

import os

import pytest

from powerforge_api.db import database_ready, get_engine


@pytest.mark.integration
def test_postgres_accepts_select() -> None:
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run live database tests.")
    get_engine.cache_clear()
    assert database_ready() is True
