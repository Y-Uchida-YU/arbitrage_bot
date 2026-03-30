from __future__ import annotations


class AdapterError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class QuoteUnavailableError(AdapterError):
    pass


class SymbolNormalizeError(AdapterError):
    pass


class VenueDegradedError(AdapterError):
    pass