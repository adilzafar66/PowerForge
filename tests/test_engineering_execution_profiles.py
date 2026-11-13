"""Versioned replay and provider neutrality, without any model/network calls."""

import subprocess
import sys


def test_provider_neutral_stage_envelopes_import_without_extraction_orm_or_sdk():
    script = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'powerforge_extraction', 'sqlalchemy', 'openai', 'celery'}:
        raise AssertionError('Unexpected import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from pydantic import BaseModel, ConfigDict
from powerforge_ai.extraction import ExtractionResponse, ExecutionUsage
class StageResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    observations: list[str]
response = ExtractionResponse[StageResult](
    result={'observations': ['source']}, usage=ExecutionUsage()
)
assert response.model_dump()['result'] == {'observations': ['source']}
restored = ExtractionResponse[StageResult].model_validate(response.model_dump())
assert restored.result.observations == ['source']
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
