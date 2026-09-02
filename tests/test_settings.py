from powerforge_shared.config import Settings


def test_database_url_normalizes_postgres_scheme() -> None:
    settings = Settings(database_url="postgres://user:pass@localhost:5432/powerforge")
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_database_url_normalizes_postgresql_scheme() -> None:
    settings = Settings(database_url="postgresql://user:pass@localhost:5432/powerforge")
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_cors_origin_list_splits_csv() -> None:
    settings = Settings(cors_origins="http://localhost:3000, http://127.0.0.1:3000")
    assert settings.cors_origin_list() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
