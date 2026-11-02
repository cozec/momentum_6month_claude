"""NYSE trading calendar for live-signal timing.

Regular full-day holidays only, built from pandas' holiday rules so no extra
dependency is needed. Unscheduled closures (e.g. national days of mourning)
are not included. Mirrors the sister Nasdaq project's calendar.
"""

from __future__ import annotations

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
    sunday_to_monday,
)
from pandas.tseries.offsets import CustomBusinessDay


class NYSEHolidayCalendar(AbstractHolidayCalendar):
    """NYSE full-day market holidays.

    Saturday holidays close the preceding Friday and Sunday holidays the
    following Monday, except New Year's Day, which is never observed on the
    prior Dec 31.
    """

    rules = [
        Holiday("New Year's Day", month=1, day=1, observance=sunday_to_monday),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01",
                observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
    ]


NYSE_SESSION = CustomBusinessDay(calendar=NYSEHolidayCalendar())


def next_session_after(day: object) -> pd.Timestamp:
    """Return the first NYSE trading day strictly after ``day``."""

    return pd.Timestamp(day).normalize() + NYSE_SESSION
