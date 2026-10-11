"""Server-side dashboard scope resolution; never accepts client identity selectors."""

from dataclasses import dataclass

from flask import session

from backend.dashboard.contracts import DashboardValidationError


class DashboardScopeError(PermissionError):
    """Safe authorization failure for a dashboard scope."""


@dataclass(frozen=True)
class DashboardScope:
    kind: str
    user_id: int
    company_id: int | None = None

    @property
    def label(self):
        return self.kind


def reject_client_identity_selectors(args):
    """Forbid client-selected identities on every private dashboard endpoint."""
    supplied = sorted({"role", "user_id", "company_id"}.intersection(args.keys()))
    if supplied:
        raise DashboardValidationError("Client-provided identity scope is not allowed.")


def resolve_dashboard_scope() -> DashboardScope:
    """Resolve platform/company/user scope only from authenticated session data."""
    user_id = session.get("user_id")
    role = session.get("role")
    if not isinstance(user_id, int):
        raise DashboardScopeError("Dashboard scope is unavailable.")
    if role == "super_admin":
        return DashboardScope(kind="platform", user_id=user_id)
    if role == "company_admin":
        company_id = session.get("company_id")
        if not isinstance(company_id, int):
            raise DashboardScopeError("Company dashboard scope is unavailable.")
        return DashboardScope(kind="company", user_id=user_id, company_id=company_id)
    if role == "customer":
        return DashboardScope(kind="user", user_id=user_id)
    raise DashboardScopeError("Dashboard scope is unavailable.")
