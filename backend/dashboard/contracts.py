"""Validation contracts shared by Phase 8 dashboard endpoints."""

from dataclasses import dataclass
from datetime import date, timedelta


MAX_DASHBOARD_RANGE_DAYS = 366
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


class DashboardValidationError(ValueError):
    """Safe client-facing validation failure for dashboard query parameters."""


@dataclass(frozen=True)
class DashboardDateRange:
    """UTC date-only range; ``end_exclusive`` makes an inclusive ``to`` safe."""

    start: str | None
    end_exclusive: str | None
    requested_to: str | None
    timezone: str

    def as_response(self):
        return {"from": self.start, "to": self.requested_to, "timezone": self.timezone}


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int

    def as_response(self, total: int):
        total_pages = (total + self.page_size - 1) // self.page_size if total else 0
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total": total,
            "total_pages": total_pages,
        }


def _parse_date(value, parameter):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise DashboardValidationError(f"{parameter} must use YYYY-MM-DD format.") from exc


def parse_date_range(args) -> DashboardDateRange:
    """Parse optional inclusive UTC dates used against SQLite UTC timestamps.

    The project stores generated timestamps through SQLite ``datetime('now')``;
    that is UTC.  Timezone conversion is deliberately deferred until the data
    model records user/company timezone preferences, so only UTC is accepted.
    """
    timezone = (args.get("timezone") or "UTC").strip().upper()
    if timezone != "UTC":
        raise DashboardValidationError("timezone must be UTC for the current timestamp model.")

    from_date = _parse_date(args.get("from"), "from")
    to_date = _parse_date(args.get("to"), "to")
    if from_date and to_date:
        if from_date > to_date:
            raise DashboardValidationError("from must not be later than to.")
        if (to_date - from_date).days > MAX_DASHBOARD_RANGE_DAYS:
            raise DashboardValidationError(f"Date ranges cannot exceed {MAX_DASHBOARD_RANGE_DAYS} days.")

    return DashboardDateRange(
        start=from_date.isoformat() if from_date else None,
        end_exclusive=(to_date + timedelta(days=1)).isoformat() if to_date else None,
        requested_to=to_date.isoformat() if to_date else None,
        timezone=timezone,
    )


def parse_pagination(args) -> Pagination:
    """Parse the future operational-list pagination contract without mutating old APIs."""
    def integer(name, default):
        raw = args.get(name)
        if raw in (None, ""):
            return default
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise DashboardValidationError(f"{name} must be an integer.") from exc

    page = integer("page", 1)
    page_size = integer("page_size", DEFAULT_PAGE_SIZE)
    if page < 1:
        raise DashboardValidationError("page must be at least 1.")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise DashboardValidationError(f"page_size must be between 1 and {MAX_PAGE_SIZE}.")
    return Pagination(page=page, page_size=page_size)
