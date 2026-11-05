"""Calendar-validated, day-first temporal parsing shared by inference and imports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any

TEMPORAL_TYPES = frozenset({"date", "time", "datetime", "timestamp", "timestamptz", "timetz"})
_MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
_MONTH_NUMBERS = {
    spelling: index for index, name in enumerate(_MONTHS, 1) for spelling in (name, name[:3])
}
_DATE_PATTERNS = (
    (r"(\d{4})([-/.])(\d{1,2})\2(\d{1,2})", "year"),
    (r"(\d{1,2})([-/.])(\d{1,2})\2(\d{4})", "day"),
    (r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", "day_name"),
    (r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", "month_name"),
)
_TIME_PATTERN = re.compile(
    r"(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?"
    r"(?:\s*([AaPp][Mm]))?(Z|[+-]\d{2}:?\d{2})?"
)


@dataclass(frozen=True)
class ParsedTemporal:
    value: date | datetime | time
    data_type: str
    format: str


def is_temporal(data_type: str | None) -> bool:
    return data_type is not None and data_type.strip().lower() in TEMPORAL_TYPES


def validate_datetime_format(data_type: str | None, fmt: str | None) -> None:
    """Reject malformed format configuration before any database writes."""
    if fmt is None:
        return
    if not isinstance(fmt, str) or not fmt:
        raise ValueError("datetime_format must be a non-empty Python strptime format string")
    if not is_temporal(data_type):
        raise ValueError("datetime_format requires a temporal type")
    representative = datetime(2004, 2, 29, 12, 34, 56, 123456, timezone.utc)
    try:
        datetime.strptime(representative.strftime(fmt), fmt)
    except (ValueError, re.error) as exc:
        raise ValueError(f"Invalid datetime_format {fmt!r}: {exc}") from exc


def _parse_time(value: str, *, datetime_component: bool = False) -> ParsedTemporal:
    match = _TIME_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("not a supported time")
    hour, minute, second, fraction, am_pm, offset = match.groups()
    if fraction and len(fraction) > 6:
        raise ValueError(
            "sub-microsecond precision requires explicit text or epoch-nanosecond storage"
        )
    hour_value = int(hour)
    if am_pm:
        if not 1 <= hour_value <= 12:
            raise ValueError("12-hour clock hour must be between 1 and 12")
        hour_value = hour_value % 12 + (12 if am_pm.lower() == "pm" else 0)
    tz = None
    if offset:
        normalised_offset = "+00:00" if offset == "Z" else offset
        # fromisoformat validates numeric offsets without using the local timezone.
        digits = normalised_offset.replace(":", "")
        if int(digits[1:3]) > 23 or int(digits[3:]) > 59:
            raise ValueError("invalid UTC offset")
        if not datetime_component and int(digits[1:3]) > 15:
            raise ValueError("time UTC offset must be less than 16 hours")
        if ":" not in normalised_offset:
            normalised_offset = normalised_offset[:3] + ":" + normalised_offset[3:]
        tz = time.fromisoformat("00:00:00" + normalised_offset).tzinfo
    result = time(
        hour_value, int(minute), int(second or 0), int((fraction or "").ljust(6, "0")), tz
    )
    fmt = "%I:%M" if am_pm else "%H:%M"
    if second is not None:
        fmt += ":%S"
    if fraction:
        fmt += ".%f"
    if am_pm:
        fmt += " %p"
    if offset:
        fmt += "%z"
    return ParsedTemporal(result, "timetz" if tz else "time", fmt)


def parse_automatic(value: str) -> ParsedTemporal:
    """Parse common formats; numeric month-first dates are deliberately excluded."""
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        if not 19700101 <= int(value) <= 20991231:
            raise ValueError("compact date outside automatic range 19700101..20991231")
        return ParsedTemporal(datetime.strptime(value, "%Y%m%d").date(), "date", "%Y%m%d")

    for pattern, order in _DATE_PATTERNS:
        match = re.match(pattern + r"(?=$|[Tt\s])", value)
        if match is None:
            continue
        parts = match.groups()
        if order == "year":
            year, separator, month, day = parts
            fmt = f"%Y{separator}%m{separator}%d"
        elif order == "day":
            day, separator, month, year = parts
            fmt = f"%d{separator}%m{separator}%Y"
        else:
            if order == "day_name":
                day, month_name, year = parts
            else:
                month_name, day, year = parts
            month_number = _MONTH_NUMBERS.get(month_name.lower())
            if month_number is None:
                raise ValueError("unknown English month name")
            month = str(month_number)
            month_fmt = "%b" if len(month_name) == 3 else "%B"
            fmt = (
                f"%d {month_fmt} %Y"
                if order == "day_name"
                else f"{month_fmt} %d{',' if ',' in match[0] else ''} %Y"
            )
        parsed_date = date(int(year), int(month), int(day))
        rest = value[match.end() :]
        if not rest:
            return ParsedTemporal(parsed_date, "date", fmt)
        separator = rest[0]
        parsed_time = _parse_time(rest[1:].strip(), datetime_component=True)
        assert isinstance(parsed_time.value, time)
        result = datetime.combine(parsed_date, parsed_time.value)
        return ParsedTemporal(
            result,
            "timestamptz" if result.tzinfo else "datetime",
            fmt + separator + parsed_time.format,
        )
    return _parse_time(value)


def infer_temporal(values: list[str]) -> tuple[str | None, set[str]]:
    """Infer a temporal type only if every non-empty value is compatible."""
    kinds: set[str] = set()
    formats: set[str] = set()
    for value in values:
        if not value.strip():
            continue
        try:
            parsed = parse_automatic(value)
        except ValueError:
            return None, set()
        kinds.add(parsed.data_type)
        formats.add(parsed.format)
    if not kinds:
        return None, set()
    if kinds <= {"date", "datetime"}:
        return ("datetime" if "datetime" in kinds else "date"), formats
    if len(kinds) == 1:
        return next(iter(kinds)), formats
    return None, set()


class TemporalInference:
    """Incrementally summarise a bounded sample without retaining its cell values."""

    def __init__(self) -> None:
        self.kinds: set[str] = set()
        self.formats: set[str] = set()
        self.valid = True
        self.has_submicrosecond_value = False

    def add(self, value: str) -> None:
        if not value.strip():
            return
        try:
            parsed = parse_automatic(value)
        except ValueError as exc:
            self.valid = False
            if "sub-microsecond" in str(exc):
                self.has_submicrosecond_value = True
            return
        self.kinds.add(parsed.data_type)
        self.formats.add(parsed.format)

    def result(self) -> tuple[str | None, set[str]]:
        if not self.valid or not self.kinds:
            return None, set()
        if self.kinds <= {"date", "datetime"}:
            kind = "datetime" if "datetime" in self.kinds else "date"
            return kind, self.formats
        if len(self.kinds) == 1:
            return next(iter(self.kinds)), self.formats
        return None, set()


def parse_temporal(value: Any, data_type: str, fmt: str | None = None) -> str:
    """Return canonical database-independent text, preserving timezone semantics."""
    kind = data_type.lower().strip()
    if isinstance(value, (datetime, date, time)):
        parsed_value = value
    elif fmt is not None:
        parsed_datetime = datetime.strptime(str(value).strip(), fmt)
        if kind == "date":
            if parsed_datetime.tzinfo is not None or parsed_datetime.time() != time():
                raise ValueError("date format must not discard a time or timezone")
            parsed_value = parsed_datetime.date()
        elif kind in ("time", "timetz"):
            parsed_value = parsed_datetime.timetz()
        else:
            parsed_value = parsed_datetime
    else:
        parsed_value = parse_automatic(str(value)).value
    if kind == "date":
        if isinstance(parsed_value, datetime) or not isinstance(parsed_value, date):
            raise ValueError("expected a date without a time")
        return parsed_value.isoformat()
    if kind in ("time", "timetz"):
        if not isinstance(parsed_value, time):
            raise ValueError("expected a time without a date")
        if (parsed_value.tzinfo is not None) != (kind == "timetz"):
            raise ValueError("time timezone does not match configured type")
        offset = parsed_value.utcoffset()
        if offset is not None and abs(offset.total_seconds()) >= 16 * 3600:
            raise ValueError("time UTC offset must be less than 16 hours")
        return parsed_value.isoformat()
    if isinstance(parsed_value, date) and not isinstance(parsed_value, datetime):
        parsed_value = datetime.combine(parsed_value, time())
    if not isinstance(parsed_value, datetime):
        raise ValueError("expected a datetime")
    if (parsed_value.tzinfo is not None) != (kind == "timestamptz"):
        raise ValueError("datetime timezone does not match configured type")
    if kind == "timestamptz":
        parsed_value = parsed_value.astimezone(timezone.utc)
    return parsed_value.isoformat(sep=" ")


def iso_to_epoch_ns(value: str) -> int:
    """Convert an offset-aware ISO timestamp to signed 64-bit epoch nanoseconds."""
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?"
        r"(Z|[+-]\d{2}:?\d{2})",
        value.strip(),
    )
    if match is None:
        raise ValueError(
            "expected an ISO datetime with an explicit UTC offset and <=9 fractional digits"
        )
    base, fraction, offset = match.groups()
    parsed = datetime.strptime(base.replace(" ", "T") + offset, "%Y-%m-%dT%H:%M:%S%z")
    delta = parsed.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    result = (delta.days * 86400 + delta.seconds) * 1_000_000_000
    result += int((fraction or "").ljust(9, "0"))
    if not -(2**63) <= result <= 2**63 - 1:
        raise ValueError("epoch nanoseconds exceed signed 64-bit range")
    return result
