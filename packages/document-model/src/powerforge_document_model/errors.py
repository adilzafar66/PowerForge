"""Domain-local validation errors. The API layer maps these in PR-06."""


class DocumentValidationError(ValueError):
    """Base class for document-domain validation failures."""


class InvalidFilename(DocumentValidationError):
    """Filename is empty or not a usable basename after sanitizing."""


class UnsupportedExtension(DocumentValidationError):
    """File extension is not in the allow-list."""
