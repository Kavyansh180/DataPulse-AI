import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("datapulse.dashboard.api")


class DashboardApiError(Exception):
    """Exception raised when an API request to the DataPulse backend fails."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        details: Optional[Any] = None,
        response_body: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details
        self.response_body = response_body


class DataPulseApiClient:
    """HTTP client wrapper communicating with the DataPulse AI FastAPI backend."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        token: Optional[str] = None,
    ):
        configured_url = (
            base_url
            or os.environ.get("DATAPULSE_API_URL")
            or os.environ.get("BACKEND_URL")
            or "http://127.0.0.1:8000"
        )
        self.base_url = configured_url.rstrip("/")
        self.timeout = timeout
        self.token = token

    def set_token(self, token: Optional[str]) -> None:
        """Update or clear the active JWT access token."""
        self.token = token

    def clear_token(self) -> None:
        """Clear the active JWT access token."""
        self.token = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self, custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Construct request headers including JWT Bearer Authorization when token is present."""
        headers = dict(custom_headers or {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Parse JSON response and translate HTTP error codes into clean DashboardApiError."""
        try:
            data = response.json()
        except Exception:
            data = None

        if response.is_success:
            return data if data is not None else {}

        # Extract structured error if returned by backend API
        error_code = None
        message = None
        details = None

        if response.status_code == 401:
            error_code = "UNAUTHORIZED"

        if isinstance(data, dict):
            # 1. Structured application error format: {"error": {"code": ..., "message": ..., "details": ...}}
            if "error" in data and isinstance(data["error"], dict):
                err = data["error"]
                error_code = err.get("code") or error_code
                message = err.get("message")
                details = err.get("details")

            # 2. FastAPI validation / detail format: {"detail": [...]}
            if "detail" in data:
                detail_val = data["detail"]
                if details is None:
                    details = detail_val

                if isinstance(detail_val, list):
                    item_strs = []
                    for item in detail_val:
                        if isinstance(item, dict):
                            loc = " -> ".join(str(x) for x in item.get("loc", []))
                            msg = item.get("msg") or item.get("message", "")
                            item_strs.append(f"{loc}: {msg}" if loc else msg)
                        else:
                            item_strs.append(str(item))
                    if item_strs:
                        formatted_detail_msg = "; ".join(item_strs)
                        if not message or response.status_code == 422:
                            message = f"Validation Error (422): {formatted_detail_msg}"
                elif isinstance(detail_val, str) and not message:
                    message = detail_val

            # 3. If details came from error.details and status is 422, format specific loc and msg
            if response.status_code == 422 and isinstance(details, list) and (not message or message == "Input validation failed for the submitted payload."):
                item_strs = []
                for item in details:
                    if isinstance(item, dict):
                        loc = item.get("loc")
                        if isinstance(loc, list):
                            loc_str = " -> ".join(str(x) for x in loc)
                        else:
                            loc_str = str(item.get("field") or "")
                        msg = item.get("msg") or item.get("message", "")
                        item_strs.append(f"{loc_str}: {msg}" if loc_str else msg)
                if item_strs:
                    message = f"Validation Error (422): {'; '.join(item_strs)}"

        if not message:
            message = f"HTTP {response.status_code}: {response.reason_phrase or 'Request failed'}"

        raise DashboardApiError(
            message=message,
            status_code=response.status_code,
            error_code=error_code,
            details=details,
            response_body=data if data is not None else response.text,
        )

    # -------------------------------------------------------------------------
    # Authentication Endpoints
    # -------------------------------------------------------------------------

    def register(self, email: str, password: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        """Register a new user account and automatically store the issued JWT token."""
        url = self._url("/api/v1/auth/register")
        payload: Dict[str, Any] = {
            "email": email.strip(),
            "password": password,
        }
        if full_name and full_name.strip():
            payload["full_name"] = full_name.strip()

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, json=payload)
                data = self._handle_response(res)
                if "access_token" in data:
                    self.set_token(data["access_token"])
                return data
        except httpx.ConnectError:
            raise DashboardApiError(
                f"Cannot connect to DataPulse backend at {self.base_url}.",
                status_code=503,
                error_code="CONNECTION_REFUSED",
            )
        except httpx.TimeoutException:
            raise DashboardApiError("Registration request timed out.", status_code=504, error_code="TIMEOUT")

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user with email and password and store the issued JWT token."""
        url = self._url("/api/v1/auth/login")
        payload = {
            "email": email.strip(),
            "password": password,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, json=payload)
                data = self._handle_response(res)
                if "access_token" in data:
                    self.set_token(data["access_token"])
                return data
        except httpx.ConnectError:
            raise DashboardApiError(
                f"Cannot connect to DataPulse backend at {self.base_url}.",
                status_code=503,
                error_code="CONNECTION_REFUSED",
            )
        except httpx.TimeoutException:
            raise DashboardApiError("Login request timed out.", status_code=504, error_code="TIMEOUT")

    def get_me(self) -> Dict[str, Any]:
        """Fetch authenticated user profile."""
        url = self._url("/api/v1/auth/me")
        try:
            with httpx.Client(timeout=10.0, headers=self._headers()) as client:
                res = client.get(url)
                return self._handle_response(res)
        except httpx.ConnectError:
            raise DashboardApiError(
                f"Cannot reach DataPulse backend at {self.base_url}.",
                status_code=503,
                error_code="CONNECTION_REFUSED",
            )
        except httpx.TimeoutException:
            raise DashboardApiError("Profile request timed out.", status_code=504, error_code="TIMEOUT")

    # -------------------------------------------------------------------------
    # Health & System Probes
    # -------------------------------------------------------------------------

    def check_health(self) -> Dict[str, Any]:
        """Call GET /health to verify backend process vitality."""
        url = self._url("/health")
        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.get(url)
                return self._handle_response(res)
        except httpx.ConnectError:
            raise DashboardApiError(
                f"Cannot connect to DataPulse backend at {self.base_url}. Ensure the FastAPI server is running.",
                status_code=503,
                error_code="CONNECTION_REFUSED",
            )
        except httpx.TimeoutException:
            raise DashboardApiError(
                "Health check request timed out.",
                status_code=504,
                error_code="TIMEOUT",
            )

    def check_readiness(self) -> Dict[str, Any]:
        """Call GET /api/v1/ready (with /ready fallback) to verify database connection."""
        url = self._url("/api/v1/ready")
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                if res.status_code == 404:
                    res = client.get(self._url("/ready"))
                return self._handle_response(res)
        except httpx.ConnectError:
            raise DashboardApiError(
                f"Cannot reach DataPulse backend at {self.base_url}.",
                status_code=503,
                error_code="CONNECTION_REFUSED",
            )
        except httpx.TimeoutException:
            raise DashboardApiError(
                "Readiness check request timed out.",
                status_code=504,
                error_code="TIMEOUT",
            )

    # -------------------------------------------------------------------------
    # Protected Dataset Endpoints
    # -------------------------------------------------------------------------

    def list_datasets(self, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch list of registered datasets owned by authenticated user."""
        url = self._url(f"/api/v1/datasets?skip={skip}&limit={limit}")
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.get(url)
                return self._handle_response(res)
        except httpx.RequestError as exc:
            raise DashboardApiError(f"Network error fetching datasets: {exc}")

    def get_dataset(self, dataset_id: int) -> Dict[str, Any]:
        """Retrieve dataset details including version snapshots."""
        url = self._url(f"/api/v1/datasets/{dataset_id}")
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.get(url)
                return self._handle_response(res)
        except httpx.RequestError as exc:
            raise DashboardApiError(f"Network error fetching dataset {dataset_id}: {exc}")

    def upload_csv(
        self,
        file_bytes: bytes,
        filename: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        version_tag: Optional[str] = None,
        dataset_name: Optional[str] = None,
        expected_schema: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload multipart CSV dataset for S3 storage and synchronous profiling."""
        url = self._url("/api/v1/datasets/upload")

        resolved_name = (name or dataset_name or "").strip()
        if not resolved_name:
            stem = Path(filename).stem.strip()
            resolved_name = stem if stem else filename.strip() or "dataset"

        files = {"file": (filename, file_bytes, "text/csv")}
        data: Dict[str, Any] = {"name": resolved_name}

        if description and description.strip():
            data["description"] = description.strip()

        if version_tag and version_tag.strip():
            data["version_tag"] = version_tag.strip()

        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.post(url, files=files, data=data)
                return self._handle_response(res)
        except httpx.ConnectError:
            raise DashboardApiError(
                f"Cannot connect to backend at {self.base_url} to upload CSV.",
                status_code=503,
                error_code="CONNECTION_REFUSED",
            )
        except httpx.TimeoutException:
            raise DashboardApiError(
                "Upload and profiling timed out. Consider a smaller file or increasing timeout.",
                status_code=504,
                error_code="TIMEOUT",
            )

    def list_runs_for_dataset(self, dataset_id: int) -> List[Dict[str, Any]]:
        """Retrieve historical profiling runs for a dataset."""
        url = self._url(f"/api/v1/datasets/{dataset_id}/runs")
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.get(url)
                return self._handle_response(res)
        except httpx.RequestError as exc:
            raise DashboardApiError(f"Network error fetching runs for dataset {dataset_id}: {exc}")

    def get_run(self, run_id: int) -> Dict[str, Any]:
        """Retrieve profiling run metadata by ID."""
        url = self._url(f"/api/v1/profiling/{run_id}")
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.get(url)
                return self._handle_response(res)
        except httpx.RequestError as exc:
            raise DashboardApiError(f"Network error fetching run {run_id}: {exc}")

    def get_run_summary(self, run_id: int) -> Dict[str, Any]:
        """Retrieve quality score and summary stats for a profiling run."""
        url = self._url(f"/api/v1/profiling/{run_id}/summary")
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.get(url)
                return self._handle_response(res)
        except httpx.RequestError as exc:
            raise DashboardApiError(f"Network error fetching summary for run {run_id}: {exc}")

    def get_run_metrics(self, run_id: int, column_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve column-level quality metrics for a profiling run."""
        url = self._url(f"/api/v1/profiling/{run_id}/metrics")
        params = {"column_name": column_name} if column_name else None
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.get(url, params=params)
                return self._handle_response(res)
        except httpx.RequestError as exc:
            raise DashboardApiError(f"Network error fetching metrics for run {run_id}: {exc}")

    def get_run_issues(self, run_id: int, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve aggregated quality issues for a profiling run."""
        url = self._url(f"/api/v1/profiling/{run_id}/issues")
        params = {"severity": severity} if severity else None
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.get(url, params=params)
                return self._handle_response(res)
        except httpx.RequestError as exc:
            raise DashboardApiError(f"Network error fetching issues for run {run_id}: {exc}")

    def compare_runs(
        self,
        dataset_id: int,
        baseline_run_id: int,
        target_run_id: int,
    ) -> Dict[str, Any]:
        """Compare two profiling runs for the same dataset."""
        url = self._url(
            f"/api/v1/datasets/{dataset_id}/compare-runs"
            f"?baseline_run_id={baseline_run_id}&target_run_id={target_run_id}"
        )
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.get(url)
                return self._handle_response(res)
        except httpx.RequestError as exc:
            raise DashboardApiError(f"Network error comparing runs: {exc}")

    def analyze_run(
        self,
        run_id: int,
        focus_areas: Optional[List[str]] = None,
        custom_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Trigger AI Root-Cause Analysis for a completed profiling run."""
        url = self._url(f"/api/v1/profiling/{run_id}/analyze")
        payload: Dict[str, Any] = {}
        if focus_areas:
            payload["focus_areas"] = focus_areas
        if custom_context:
            payload["custom_context"] = custom_context

        try:
            with httpx.Client(timeout=45.0, headers=self._headers()) as client:
                res = client.post(url, json=payload if payload else None)
                return self._handle_response(res)
        except httpx.ConnectError:
            raise DashboardApiError(
                f"Cannot connect to backend at {self.base_url} to run AI analysis.",
                status_code=503,
                error_code="CONNECTION_REFUSED",
            )
        except httpx.TimeoutException:
            raise DashboardApiError(
                "AI Root-Cause Analysis request timed out. The LLM provider took too long to respond.",
                status_code=504,
                error_code="TIMEOUT",
            )

    def preview_remediation(
        self,
        run_id: int,
        operations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Simulate and preview remediation operations for a completed run."""
        url = self._url(f"/api/v1/profiling/{run_id}/remediation/preview")
        payload = {"operations": operations}
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.post(url, json=payload)
                return self._handle_response(res)
        except httpx.ConnectError:
            raise DashboardApiError(
                f"Cannot connect to backend at {self.base_url} to preview remediation.",
                status_code=503,
                error_code="CONNECTION_REFUSED",
            )
        except httpx.TimeoutException:
            raise DashboardApiError(
                "Remediation preview timed out.",
                status_code=504,
                error_code="TIMEOUT",
            )

    def apply_remediation(
        self,
        run_id: int,
        preview_id: str,
        operations: List[Dict[str, Any]],
        new_version_tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply approved remediation, store new artifact, and revalidate."""
        url = self._url(f"/api/v1/profiling/{run_id}/remediation/apply")
        payload: Dict[str, Any] = {
            "preview_id": preview_id,
            "operations": operations,
        }
        if new_version_tag:
            payload["new_version_tag"] = new_version_tag

        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.post(url, json=payload)
                return self._handle_response(res)
        except httpx.ConnectError:
            raise DashboardApiError(
                f"Cannot connect to backend at {self.base_url} to apply remediation.",
                status_code=503,
                error_code="CONNECTION_REFUSED",
            )
        except httpx.TimeoutException:
            raise DashboardApiError(
                "Remediation apply and revalidation timed out.",
                status_code=504,
                error_code="TIMEOUT",
            )

    def get_dataset_remediation_history(self, dataset_id: int) -> List[Dict[str, Any]]:
        """Retrieve remediation audit history for a dataset."""
        url = self._url(f"/api/v1/datasets/{dataset_id}/remediation-history")
        try:
            with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
                res = client.get(url)
                return self._handle_response(res)
        except httpx.RequestError as exc:
            raise DashboardApiError(f"Network error fetching remediation history: {exc}")
