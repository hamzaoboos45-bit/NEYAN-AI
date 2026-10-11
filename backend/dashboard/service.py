"""Application service for the first Phase 8 dashboard KPI endpoint."""

from datetime import datetime, timezone

from backend.dashboard.repository import DashboardRepository


class DashboardService:
    def __init__(self, repository=None):
        self._repository = repository or DashboardRepository()

    def overview(self, scope, date_range):
        return {
            "data": self._repository.initial_metrics(scope, date_range),
            "scope": scope.label,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "date_range": date_range.as_response(),
        }

    def user_home(self, scope):
        if scope.kind != "user":
            raise ValueError("Customer dashboard scope is required.")
        return {
            "data": self._repository.user_home_dashboard(scope.user_id),
            "scope": scope.label,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }

    def admin(self, scope, date_range):
        return {
            "data": self._repository.admin_dashboard(scope, date_range),
            "scope": scope.label,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "date_range": date_range.as_response(),
        }
