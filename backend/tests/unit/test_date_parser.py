"""Date parser covers the formats that actually appear in prod invoices.

Cases drawn from the live deploy's `vendors` page: April 30, 1999;
9/21/20 - 9/26/20; OCTOBER 2020; 052199; 10/30/2020; Feb 28, 20; 01-Oct-2001.
"""

from __future__ import annotations

import pytest

from app.domain.date_parser import parse_date_or_range


class TestPointDates:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("April 30, 1999", "1999-04-30"),
            ("May 19, 1999", "1999-05-19"),
            ("June 16, 1999", "1999-06-16"),
            ("Feb 28, 20", "2020-02-28"),
            ("7/26/99", "1999-07-26"),
            ("12/1/2016", "2016-12-01"),
            ("10/30/2020", "2020-10-30"),
            ("4/15/2020", "2020-04-15"),
            ("01-Oct-2001", "2001-10-01"),
            ("2026-05-13", "2026-05-13"),
        ],
    )
    def test_common_us_formats(self, text: str, expected: str) -> None:
        iso_from, iso_to = parse_date_or_range(text)
        assert iso_from == expected
        assert iso_to == expected, "point date should set iso_from == iso_to"


class TestMonthOnlyDates:
    def test_month_year_fans_out_to_full_month(self) -> None:
        iso_from, iso_to = parse_date_or_range("October 2020")
        assert iso_from == "2020-10-01"
        assert iso_to == "2020-10-31"

    def test_short_month_year(self) -> None:
        iso_from, iso_to = parse_date_or_range("Oct 2020")
        assert iso_from == "2020-10-01"
        assert iso_to == "2020-10-31"

    def test_short_month_dash_year(self) -> None:
        iso_from, iso_to = parse_date_or_range("Feb-99")
        assert iso_from == "1999-02-01"
        assert iso_to == "1999-02-28"


class TestRanges:
    def test_billing_period(self) -> None:
        iso_from, iso_to = parse_date_or_range("9/21/20 - 9/26/20")
        assert iso_from == "2020-09-21"
        assert iso_to == "2020-09-26"

    def test_em_dash_range(self) -> None:
        iso_from, iso_to = parse_date_or_range("4/1/2020 — 4/30/2020")
        assert iso_from == "2020-04-01"
        assert iso_to == "2020-04-30"

    def test_partial_range_returns_none(self) -> None:
        """If either side of a range is unparseable, return (None, None).

        Better to filter the row out of date queries than to guess.
        """
        iso_from, iso_to = parse_date_or_range("Q3 2020 - 9/26/20")
        assert iso_from is None
        assert iso_to is None


class TestUnparseable:
    @pytest.mark.parametrize("text", ["", "  ", "052199", "n/a", "see attached"])
    def test_garbage_returns_none(self, text: str) -> None:
        assert parse_date_or_range(text) == (None, None)

    def test_none_input(self) -> None:
        assert parse_date_or_range(None) == (None, None)
