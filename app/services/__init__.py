"""Business logic services for DataPulse AI.

Exports are loaded lazily to ensure database-independent services (such as
ProfilerService and RemediationEngine) can be imported without initializing
database engines, models, or network clients.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.dataset_service import DatasetService
    from app.services.audit_service import AuditService
    from app.services.s3_service import S3Service
    from app.services.csv_service import CSVValidationService
    from app.services.profiler_service import ProfilerService
    from app.services.profiling_service import ProfilingService
    from app.services.comparison_service import ComparisonService
    from app.services.remediation_engine import RemediationEngine
    from app.services.remediation_service import RemediationService

__all__ = [
    "DatasetService",
    "AuditService",
    "S3Service",
    "CSVValidationService",
    "ProfilerService",
    "ProfilingService",
    "ComparisonService",
    "RemediationEngine",
    "RemediationService",
]

_SERVICE_MAP = {
    "DatasetService": ("app.services.dataset_service", "DatasetService"),
    "AuditService": ("app.services.audit_service", "AuditService"),
    "S3Service": ("app.services.s3_service", "S3Service"),
    "CSVValidationService": ("app.services.csv_service", "CSVValidationService"),
    "ProfilerService": ("app.services.profiler_service", "ProfilerService"),
    "ProfilingService": ("app.services.profiling_service", "ProfilingService"),
    "ComparisonService": ("app.services.comparison_service", "ComparisonService"),
    "RemediationEngine": ("app.services.remediation_engine", "RemediationEngine"),
    "RemediationService": ("app.services.remediation_service", "RemediationService"),
}


def __getattr__(name: str):
    if name in _SERVICE_MAP:
        import importlib
        mod_name, attr_name = _SERVICE_MAP[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
