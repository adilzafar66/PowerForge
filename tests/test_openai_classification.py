"""OpenAI adapter contract. The SDK client is injected and no socket is opened."""

from __future__ import annotations

import base64
import socket
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from extraction_worker.openai_classification import OpenAIClassificationProvider
from powerforge_ai.providers import (
    ClassificationImageInput,
    ClassificationTextExcerpt,
    ClassifyDocumentRequest,
    ClassifyPageInput,
    ClassifyPagesRequest,
    DocumentClassificationResponse,
    DocumentClassificationResult,
    PageClassificationResponse,
    PageClassificationResult,
)
from powerforge_document_classification.errors import (
    ClassificationErrorCode,
    ClassificationProviderError,
)
from powerforge_shared.config import Settings


class _ScriptedResponses:
    def __init__(self, items: list[object]) -> None:
        self.items = list(items)
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _ScriptedClient:
    def __init__(self, items: list[object]) -> None:
        self.responses = _ScriptedResponses(items)


@pytest.fixture(autouse=True)
def _no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("adapter test opened a socket")

    monkeypatch.setattr(socket, "create_connection", blocked)


def _settings() -> Settings:
    return Settings(
        ai_provider="openai",
        ai_classification_model="gpt-test-model",
        ai_classification_reasoning_effort="medium",
        ai_classification_image_detail="high",
        ai_classification_timeout_seconds=15,
        openai_api_key="sk-test",
    )


def _image() -> ClassificationImageInput:
    return ClassificationImageInput(page_number=1, mime_type="image/webp", data=b"RIFFWEBP")


def _document_request() -> ClassifyDocumentRequest:
    return ClassifyDocumentRequest(
        filename="sheet.pdf",
        extension=".pdf",
        page_count=1,
        text_excerpts=[ClassificationTextExcerpt(page_number=1, text="bus rating")],
        images=[_image()],
        allowed_types=("SINGLE_LINE_DIAGRAM",),
        instructions="Choose a document class.",
    )


def _usage() -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=11,
        output_tokens=7,
        input_tokens_details=SimpleNamespace(cached_tokens=2),
        output_tokens_details=SimpleNamespace(reasoning_tokens=1),
    )


def _parsed_document() -> SimpleNamespace:
    return SimpleNamespace(
        id="resp_doc",
        output=[],
        output_parsed=DocumentClassificationResult(
            predicted_type="SINGLE_LINE_DIAGRAM",
            confidence_score=0.91,
            rationale="One line.",
        ),
        usage=_usage(),
    )


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/responses")


def _status(status_code: int, error_type: type[Exception]) -> Exception:
    response = httpx.Response(status_code, request=_request())
    return error_type("provider error", response=response, body=None)


def test_document_call_uses_responses_structured_output_and_maps_usage() -> None:
    client = _ScriptedClient([_parsed_document()])
    provider = OpenAIClassificationProvider(_settings(), client)
    result = provider.classify_document(_document_request())
    assert isinstance(result, DocumentClassificationResponse)
    assert isinstance(result.result, DocumentClassificationResult)
    assert type(result).__module__.startswith("powerforge_ai")
    assert type(result.result).__module__.startswith("powerforge_ai")
    assert result.result.predicted_type == "SINGLE_LINE_DIAGRAM"
    assert result.usage.provider == "openai"
    assert result.usage.model == "gpt-test-model"
    assert result.usage.provider_response_id == "resp_doc"
    assert result.usage.input_tokens == 11
    assert result.usage.cached_input_tokens == 2
    assert result.usage.output_tokens == 7
    assert result.usage.reasoning_tokens == 1
    assert result.usage.image_count == 1
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test-model"
    assert call["store"] is False
    assert call["text_format"] is DocumentClassificationResult
    assert issubclass(call["text_format"], BaseModel)
    assert call["reasoning"] == {"effort": "medium"}
    assert call["timeout"] == 15.0
    assert call["instructions"] == "Choose a document class."
    assert "tools" not in call
    assert "background" not in call
    assert "conversation" not in call
    parts = call["input"][0]["content"]
    image = next(part for part in parts if part["type"] == "input_image")
    assert image["detail"] == "high"
    assert image["image_url"].startswith("data:image/webp;base64,")
    encoded = image["image_url"].split(",", 1)[1]
    assert base64.b64decode(encoded) == b"RIFFWEBP"
    assert "sheet.pdf" in parts[0]["text"]
    assert not any(part["type"] == "input_file" for part in parts)


def test_page_call_sends_image_bytes_and_returns_page_results() -> None:
    parsed = SimpleNamespace(
        id="resp_pages",
        output=[],
        output_parsed={
            "pages": [
                {
                    "page_number": 1,
                    "predicted_type": "ELECTRICAL_DRAWING",
                    "confidence_score": 0.8,
                }
            ]
        },
        usage=_usage(),
    )
    client = _ScriptedClient([parsed])
    provider = OpenAIClassificationProvider(_settings(), client)
    request = ClassifyPagesRequest(
        filename="sheet.pdf",
        extension=".pdf",
        pages=[ClassifyPageInput(page_number=1, text="panel", image=_image())],
        allowed_types=("ELECTRICAL_DRAWING",),
        instructions="Choose a page class.",
    )
    result = provider.classify_pages(request)
    assert isinstance(result, PageClassificationResponse)
    assert isinstance(result.pages[0], PageClassificationResult)
    assert result.pages[0].predicted_type == "ELECTRICAL_DRAWING"
    assert result.usage.image_count == 1
    call = client.responses.calls[0]
    assert call["text_format"].model_fields.keys() == {"pages"}
    assert "tools" not in call
    image = next(
        part for part in call["input"][0]["content"] if part["type"] == "input_image"
    )
    assert image["detail"] == "high"
    assert base64.b64decode(image["image_url"].split(",", 1)[1]) == b"RIFFWEBP"


def test_refusal_is_not_retried() -> None:
    refused = SimpleNamespace(
        id="resp_refuse",
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="refusal", refusal="no")],
            )
        ],
        output_parsed=None,
        usage=_usage(),
    )
    client = _ScriptedClient([refused])
    provider = OpenAIClassificationProvider(_settings(), client)
    with pytest.raises(ClassificationProviderError) as caught:
        provider.classify_document(_document_request())
    assert caught.value.code == ClassificationErrorCode.PROVIDER_REFUSAL
    assert len(client.responses.calls) == 1


def test_auth_is_not_retried_and_rate_limit_retries_twice() -> None:
    import openai

    auth = _ScriptedClient([_status(401, openai.AuthenticationError)])
    provider = OpenAIClassificationProvider(_settings(), auth)
    with pytest.raises(ClassificationProviderError) as caught:
        provider.classify_document(_document_request())
    assert caught.value.code == ClassificationErrorCode.PROVIDER_AUTH_ERROR
    assert len(auth.responses.calls) == 1

    limited = _ScriptedClient(
        [
            _status(429, openai.RateLimitError),
            _status(429, openai.RateLimitError),
            _parsed_document(),
        ]
    )
    recovered = OpenAIClassificationProvider(_settings(), limited)
    result = recovered.classify_document(_document_request())
    assert result.result.predicted_type == "SINGLE_LINE_DIAGRAM"
    assert len(limited.responses.calls) == 3

    exhausted = _ScriptedClient([_status(429, openai.RateLimitError) for _ in range(3)])
    failing = OpenAIClassificationProvider(_settings(), exhausted)
    with pytest.raises(ClassificationProviderError) as limited_error:
        failing.classify_document(_document_request())
    assert limited_error.value.code == ClassificationErrorCode.PROVIDER_RATE_LIMITED
    assert len(exhausted.responses.calls) == 3


def test_timeout_and_unavailable_retry_then_map() -> None:
    import openai

    request = _request()
    timed = _ScriptedClient([openai.APITimeoutError(request) for _ in range(3)])
    provider = OpenAIClassificationProvider(_settings(), timed)
    with pytest.raises(ClassificationProviderError) as timeout_error:
        provider.classify_document(_document_request())
    assert timeout_error.value.code == ClassificationErrorCode.PROVIDER_TIMEOUT
    assert len(timed.responses.calls) == 3

    down = _ScriptedClient(
        [openai.APIConnectionError(message="down", request=request) for _ in range(3)]
    )
    unavailable = OpenAIClassificationProvider(_settings(), down)
    with pytest.raises(ClassificationProviderError) as connection_error:
        unavailable.classify_document(_document_request())
    assert connection_error.value.code == ClassificationErrorCode.PROVIDER_UNAVAILABLE

    server = _ScriptedClient([_status(500, openai.InternalServerError) for _ in range(3)])
    server_provider = OpenAIClassificationProvider(_settings(), server)
    with pytest.raises(ClassificationProviderError) as server_error:
        server_provider.classify_document(_document_request())
    assert server_error.value.code == ClassificationErrorCode.PROVIDER_UNAVAILABLE
    assert len(server.responses.calls) == 3


def test_invalid_output_is_not_retried() -> None:
    invalid = SimpleNamespace(id="resp_bad", output=[], output_parsed=None, usage=_usage())
    client = _ScriptedClient([invalid, invalid])
    provider = OpenAIClassificationProvider(_settings(), client)
    with pytest.raises(ClassificationProviderError) as caught:
        provider.classify_document(_document_request())
    assert caught.value.code == ClassificationErrorCode.INVALID_PROVIDER_RESPONSE
    assert len(client.responses.calls) == 1


def test_client_timeout_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", _FakeOpenAI)
    OpenAIClassificationProvider(_settings())
    assert captured["api_key"] == "sk-test"
    assert captured["timeout"] == 15
    assert captured["max_retries"] == 0
