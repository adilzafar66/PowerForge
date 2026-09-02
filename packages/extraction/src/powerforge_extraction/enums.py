from enum import StrEnum


class ExtractionMethod(StrEnum):
    AI_VISION = "AI_VISION"
    AI_TEXT = "AI_TEXT"
    OCR = "OCR"
    TABLE = "TABLE"
    MANUAL = "MANUAL"
