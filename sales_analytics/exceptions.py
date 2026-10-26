"""Exceptions raised by the sales analytics package."""


class SalesDataError(Exception):
    """Base exception for all sales-data loading and analysis failures."""


class SalesFileNotFoundError(SalesDataError, FileNotFoundError):
    """Raised when the CSV path does not exist or is not a regular file.

    Also a ``FileNotFoundError``, so callers can catch either.
    """


class MalformedCSVError(SalesDataError):
    """Raised when a CSV file, or one of its rows, cannot be parsed or validated.

    Attributes:
        line_number: 1-based physical line in the file (the header is line
            1), or ``None`` for file-level problems such as a missing column.
    """

    def __init__(self, message: str, line_number: int | None = None) -> None:
        """Create the error with an optional line number."""
        super().__init__(message)
        self.line_number = line_number

    def __str__(self) -> str:
        """Prefix the message with its line number when there is one."""
        message = super().__str__()
        if self.line_number is None:
            return message
        return f"line {self.line_number}: {message}"
