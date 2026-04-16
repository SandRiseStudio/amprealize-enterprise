"""Enterprise telemetry KPI projector.

Extends the OSS TelemetryKPIProjector with enterprise forecasting capabilities.

NOTE: The OSS shim (amprealize/analytics/telemetry_kpi_projector.py) provides
the standard project(events) interface used by api.py/CLI. This module provides
enterprise-specific names that are also re-exported by the shim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TelemetryProjection:
    """Data class holding a KPI projection result.

    Fields are compatible with the OSS stub interface used by api.py endpoints.
    """

    summary: Dict[str, Any] = field(default_factory=dict)
    fact_behavior_usage: List[Dict[str, Any]] = field(default_factory=list)
    fact_token_savings: List[Dict[str, Any]] = field(default_factory=list)
    fact_execution_status: List[Dict[str, Any]] = field(default_factory=list)
    fact_compliance_steps: List[Dict[str, Any]] = field(default_factory=list)
    fact_resource_usage: List[Dict[str, Any]] = field(default_factory=list)
    fact_cost_allocation: List[Dict[str, Any]] = field(default_factory=list)

    # Enterprise-only fields
    metric_name: str = ""
    current_value: float = 0.0
    projected_value: float = 0.0
    confidence: float = 0.0
    trend: str = "stable"
    period_days: int = 30
    metadata: Dict[str, Any] = field(default_factory=dict)


class TelemetryKPIProjector:
    """Enterprise KPI forecasting placeholder.

    The standard project(events) interface is provided by the OSS projector
    (amprealize/analytics/telemetry_kpi_projector.py). This class is NOT
    imported by the shim — the shim only imports TelemetryProjection from here.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._config = kwargs

    async def project_metric(self, metric_name: str, **kwargs: Any) -> TelemetryProjection:
        """Enterprise-only: project a specific KPI metric with forecasting."""
        raise NotImplementedError("Enterprise KPI forecasting not yet implemented")
