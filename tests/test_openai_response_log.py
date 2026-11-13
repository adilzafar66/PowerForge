import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from pydantic import BaseModel

from extraction_worker.openai_response_log import save_structured_response


class StructuredOutput(BaseModel):
    value: str


def test_structured_responses_are_saved_separately_without_request_data(tmp_path):
    response = SimpleNamespace(
        id="resp_test",
        status="completed",
        output_parsed=StructuredOutput(value="source text"),
        instructions="private prompt",
    )
    with ThreadPoolExecutor() as workers:
        list(workers.map(lambda _: save_structured_response(str(tmp_path), response), range(4)))

    files = list(tmp_path.iterdir())
    assert len(files) == 4
    for path in files:
        assert path.suffix == ".json"
        assert path.stat().st_mode & 0o777 == 0o600
        saved = json.loads(path.read_text())
        assert saved["output_parsed"] == {"value": "source text"}
        assert saved["response_id"] == "resp_test"
        assert "instructions" not in saved


def test_missing_structured_output_and_disabled_capture_write_nothing(tmp_path):
    save_structured_response(str(tmp_path), SimpleNamespace(output_parsed=None))
    save_structured_response("", SimpleNamespace(output_parsed={"value": "source text"}))
    assert not list(tmp_path.iterdir())
