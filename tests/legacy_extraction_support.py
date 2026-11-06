"""Reflect the historical run schema for migration tests preceding the purpose column.

The runtime mapping targets current head; historical tests must not insert future columns.
No retained runtime source is executed.
"""

from sqlalchemy import MetaData, Table
from sqlalchemy.orm import registry


def historical_run_mapper(monkeypatch, engine):
    import powerforge_extraction.persistence as persistence

    table = Table("extraction_runs", MetaData(), autoload_with=engine)

    class HistoricalRun:
        pass

    mapper_registry = registry()
    mapper_registry.map_imperatively(HistoricalRun, table)
    monkeypatch.setattr(persistence, "ExtractionRun", HistoricalRun)
    return HistoricalRun
