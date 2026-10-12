"""AI provider interfaces.

Implementations may live in workers later. The engineering model must not depend
on this package's vendor adapters (none exist in Phase 0). Classification
contracts added for Phase 4 are provider-neutral; predicted types are strings.
"""

from powerforge_ai.providers import (
    ALTERNATIVES_MAX_ITEMS,
    RATIONALE_MAX_CHARS,
    ClassificationAlternative,
    ClassificationImageInput,
    ClassificationProvider,
    ClassificationTextExcerpt,
    ClassificationUsage,
    ClassifyDocumentRequest,
    ClassifyPageInput,
    ClassifyPagesRequest,
    DocumentClassificationResponse,
    DocumentClassificationResult,
    LLMProvider,
    OCRProvider,
    PageClassificationResponse,
    PageClassificationResult,
    VisionProvider,
)

__all__ = [
    "ALTERNATIVES_MAX_ITEMS",
    "RATIONALE_MAX_CHARS",
    "ClassificationAlternative",
    "ClassificationImageInput",
    "ClassificationProvider",
    "ClassificationTextExcerpt",
    "ClassificationUsage",
    "ClassifyDocumentRequest",
    "ClassifyPageInput",
    "ClassifyPagesRequest",
    "DocumentClassificationResponse",
    "DocumentClassificationResult",
    "LLMProvider",
    "OCRProvider",
    "PageClassificationResponse",
    "PageClassificationResult",
    "VisionProvider",
]
