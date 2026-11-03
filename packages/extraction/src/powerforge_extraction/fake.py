"""Deterministic synthetic source probes. Never genuine engineering extraction."""

import time

from powerforge_ai.extraction import (
    ErrorCode,
    ExecutionUsage,
    ExtractionRequest,
    ExtractionResponse,
    ProbeResult,
    ProviderFailure,
)


class SimulatedWorkerInterruption(BaseException):
    """Test a crash without converting it into a graceful provider failure."""


class FakeExtractionProvider:
    def __init__(self, scenario: str = "success", delay_seconds: float = 0) -> None:
        self.scenario, self.delay_seconds = scenario, delay_seconds
        self.calls: list[str] = []

    def execute(self, request: ExtractionRequest) -> ExtractionResponse:
        self.calls.append(request.unit_key)
        if self.scenario == "interrupted":
            raise SimulatedWorkerInterruption()
        if self.scenario == "slow" or self.delay_seconds:
            time.sleep(self.delay_seconds or 3)
        if self.scenario == "permanent":
            raise ProviderFailure(ErrorCode.AUTH)
        if self.scenario == "transient" and request.attempt_number == 1:
            raise ProviderFailure(ErrorCode.UNAVAILABLE)
        if self.scenario == "invalid":
            raise ProviderFailure(
                ErrorCode.INVALID, ExecutionUsage(input_tokens=10, output_tokens=2)
            )
        excerpt = (request.text or "")[:80] or None
        if self.scenario == "empty":
            excerpt = None
        return ExtractionResponse(
            result=ProbeResult(acknowledged=True, excerpt=excerpt),
            usage=ExecutionUsage(
                input_tokens=len((request.text or "").encode()) // 4,
                cached_input_tokens=0,
                output_tokens=16,
            ),
        )
