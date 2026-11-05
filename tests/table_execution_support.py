"""Table execution fixtures use actual pinned artifacts and scripted observations only."""

import copy

import pytest

from engineering_execution_support import attempt as attempt
from engineering_execution_support import processing
from extraction_execution_support import execution_ctx as execution_ctx
from extraction_execution_support import start_run
from powerforge_ai.extraction import ExecutionUsage, ExtractionResponse
from powerforge_extraction.table_profiles import TABLE_TEST_PROFILE
from table_grounding_support import claims, schedule


@pytest.fixture
def table_ctx(execution_ctx):
    ctx = execution_ctx
    _, text = schedule()
    processing(ctx, native=text)
    return ctx


def start_tables(ctx, **body):
    return start_run(ctx, **{"profile_key": TABLE_TEST_PROFILE, **body})


def execute(ctx, unit_id, provider):
    """Wait for a planned attempt to admit or settle; never retry a provider call."""
    from extraction_execution_support import execute as execute_once
    from powerforge_extraction.models import ExtractionWorkUnit
    from test_extraction_celery_integration import wait_for

    def step():
        try:
            admitted = execute_once(ctx, unit_id, provider)
        except RuntimeError as error:
            from pydantic import ValidationError

            cause = error.__context__
            error.add_note(f"Underlying test execution failure: {type(cause).__name__}")
            if isinstance(cause, ValidationError):
                error.add_note(
                    str(
                        [(e["type"], e["loc"], e["msg"]) for e in cause.errors(include_input=False)]
                    )
                )
            raise
        if admitted:
            return (True,)
        with ctx["factory"]() as session:
            unit = session.get(ExtractionWorkUnit, unit_id)
            if unit is None or unit.status in {"COMPLETED", "FAILED", "CANCELLED"}:
                return (False,)
        return None

    return wait_for(step, seconds=5)[0]


def claim_ready(ctx, unit_id):
    from powerforge_extraction.orchestration import ExtractionCoordinator
    from test_extraction_celery_integration import wait_for

    def step():
        with ctx["factory"].begin() as session:
            return ExtractionCoordinator(session, ctx["settings"]).claim(unit_id)

    return wait_for(step, seconds=5)


class TableProvider:
    def __init__(
        self, *, visual=False, empty=False, failure=None, on_call=None, reconstruction=None
    ):
        self.visual, self.empty = visual, empty
        self.failure, self.on_call, self.reconstruction = failure, on_call, reconstruction
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if self.on_call:
            self.on_call(request)
        if self.failure and (failure := self.failure(request)):
            raise failure
        if request.stage == "TABLE_RECONSTRUCTION":
            result = (
                copy.deepcopy(self.reconstruction)
                if self.reconstruction
                else schedule(visual=self.visual)[0]
            )
            if self.empty:
                result["tables"] = []
        else:
            result = claims()
        return ExtractionResponse[request.response_model](
            result=result,
            usage=ExecutionUsage(input_tokens=20, cached_input_tokens=2, output_tokens=16),
        )
