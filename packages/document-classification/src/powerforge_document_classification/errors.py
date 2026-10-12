"""Classification failure codes. Provider-call timeout and task timeout stay distinct."""

from enum import StrEnum


class ClassificationErrorCode(StrEnum):
    AI_CLASSIFICATION_DISABLED = "AI_CLASSIFICATION_DISABLED"
    PROVIDER_AUTH_ERROR = "PROVIDER_AUTH_ERROR"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    CLASSIFICATION_TASK_TIMEOUT = "CLASSIFICATION_TASK_TIMEOUT"
    PROVIDER_REFUSAL = "PROVIDER_REFUSAL"
    INVALID_PROVIDER_RESPONSE = "INVALID_PROVIDER_RESPONSE"
    CLASSIFICATION_INPUT_ERROR = "CLASSIFICATION_INPUT_ERROR"
    ARTIFACT_UNAVAILABLE = "ARTIFACT_UNAVAILABLE"
    UNKNOWN_CLASSIFICATION_ERROR = "UNKNOWN_CLASSIFICATION_ERROR"


class ClassificationProviderError(Exception):
    """A provider call failed before a usable classification result existed."""

    def __init__(self, code: ClassificationErrorCode) -> None:
        self.code = code
        super().__init__(code.value)
