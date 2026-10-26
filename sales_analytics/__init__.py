"""Sales analytics over CSV data using functional programming techniques."""

from sales_analytics.analyzer import SalesAnalyzer
from sales_analytics.exceptions import (
    MalformedCSVError,
    SalesDataError,
    SalesFileNotFoundError,
)
from sales_analytics.loader import SalesDataLoader
from sales_analytics.models import (
    LoadResult,
    RowError,
    SaleRecord,
    SalesStats,
    SummaryReport,
)

__all__ = [
    "LoadResult",
    "MalformedCSVError",
    "RowError",
    "SaleRecord",
    "SalesAnalyzer",
    "SalesDataError",
    "SalesDataLoader",
    "SalesFileNotFoundError",
    "SalesStats",
    "SummaryReport",
]
