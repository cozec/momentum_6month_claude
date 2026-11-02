"""Report whether today is the first NYSE-style trading day of the month."""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def _observed_fixed(month: int, day: int, year: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(days=7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _easter(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def market_holidays(year: int) -> set[date]:
    holidays = {
        _observed_fixed(1, 1, year),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed_fixed(7, 4, year),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed_fixed(12, 25, year),
    }
    if year >= 2022:
        holidays.add(_observed_fixed(6, 19, year))
    return holidays


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in market_holidays(day.year)


def first_trading_day(year: int, month: int) -> date:
    current = date(year, month, 1)
    while not is_trading_day(current):
        current += timedelta(days=1)
    return current


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Date to evaluate in YYYY-MM-DD format.")
    parser.add_argument("--force", action="store_true", help="Always report should_run=true.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.date:
        today = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        today = datetime.now(ZoneInfo("America/New_York")).date()

    first = first_trading_day(today.year, today.month)
    should_run = args.force or today == first
    print(f"today={today}")
    print(f"first_trading_day={first}")
    print(f"should_run={str(should_run).lower()}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"today={today}\n")
            handle.write(f"first_trading_day={first}\n")
            handle.write(f"should_run={str(should_run).lower()}\n")


if __name__ == "__main__":
    main()
