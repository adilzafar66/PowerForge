"""Application-owned errors contain only bounded safe messages."""


class ExtractionError(ValueError):
    code = "invalid_extraction_request"
    status_code = 422


class ExtractionConflict(ExtractionError):
    code = "extraction_conflict"
    status_code = 409


class ExtractionDisabled(ExtractionError):
    code = "extraction_disabled"
    status_code = 409


class LeaseLost(ExtractionConflict):
    code = "extraction_lease_lost"
