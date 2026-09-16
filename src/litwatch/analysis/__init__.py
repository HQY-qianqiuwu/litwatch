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

__all__ = [
    "GatewayResponseError",
    "GatewayTimeoutError",
    "GatewayUpstreamError",
    "InvalidBaseUrlError",
    "OpenAICompatibleGateway",
    "PaperAnalysis",
    "QuickScan",
    "validate_base_url",
]
