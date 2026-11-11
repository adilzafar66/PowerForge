"""Sanitized failure reasons for bounded spatial-layout processing."""


class LayoutBound(ValueError):
    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason
