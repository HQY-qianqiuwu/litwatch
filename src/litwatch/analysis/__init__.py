"""Paper analysis boundaries."""

from litwatch.analysis.gateway import (
    GatewayResponseError,
    GatewayTimeoutError,
    GatewayUpstreamError,
    InvalidBaseUrlError,
    OpenAICompatibleGateway,
    validate_base_url,
)
from litwatch.analysis.models import PaperAnalysis, QuickScan
from litwatch.analysis.service import (
    PaperAnalysisService,
    PaperAnalysisUnavailableError,
    PaperNotFoundError,
)

__all__ = [
    "GatewayResponseError",
    "GatewayTimeoutError",
    "GatewayUpstreamError",
    "InvalidBaseUrlError",
    "OpenAICompatibleGateway",
    "PaperAnalysis",
    "PaperAnalysisService",
    "PaperAnalysisUnavailableError",
    "PaperNotFoundError",
    "QuickScan",
    "validate_base_url",
]
