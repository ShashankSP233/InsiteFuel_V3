from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Return the current application time as timezone-aware IST."""
    return datetime.now(IST)