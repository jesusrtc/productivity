from datetime import datetime

import pytest

from trustimircli.commands.incident import (
    _parse_date, _find_date_column, _filter_rows_by_date,
)


class TestParseDate:
    def test_date_only(self):
        dt = _parse_date('2026-03-10', 'since')
        assert dt == datetime(2026, 3, 10)

    def test_date_with_time(self):
        dt = _parse_date('2026-03-10 14:00', 'since')
        assert dt == datetime(2026, 3, 10, 14, 0)

    def test_invalid_format(self):
        with pytest.raises(Exception) as exc_info:
            _parse_date('March 10, 2026', 'since')
        assert 'Invalid date format' in str(exc_info.value)


class TestFindDateColumn:
    def test_finds_created(self):
        headers = ['ID', 'Title', 'Status', 'Created']
        assert _find_date_column(headers) == 3

    def test_finds_started(self):
        headers = ['ID', 'Title', 'Started']
        assert _find_date_column(headers) == 2

    def test_finds_started_at(self):
        headers = ['ID', 'Title', 'Started At']
        assert _find_date_column(headers) == 2

    def test_fallback_to_last(self):
        headers = ['ID', 'Title', 'Something']
        assert _find_date_column(headers) == 2

    def test_empty_headers(self):
        assert _find_date_column([]) is None


class TestFilterRowsByDate:
    HEADERS = ['ID', 'Title', 'Status', 'Created']
    ROWS = [
        ['101', 'Incident A', 'Active', '2026-03-10 14:00'],
        ['100', 'Incident B', 'Active', '2026-03-09 10:30'],
        ['99', 'Incident C', 'Closed', '2026-03-05 08:00'],
        ['98', 'Incident D', 'Closed', '2026-02-28 12:00'],
    ]

    def test_since_only(self):
        since = datetime(2026, 3, 9)
        result = _filter_rows_by_date(self.HEADERS, self.ROWS, since, None)
        assert len(result) == 2
        assert result[0][0] == '101'
        assert result[1][0] == '100'

    def test_until_only(self):
        until = datetime(2026, 3, 6)
        result = _filter_rows_by_date(self.HEADERS, self.ROWS, None, until)
        assert len(result) == 2
        assert result[0][0] == '99'
        assert result[1][0] == '98'

    def test_since_and_until(self):
        since = datetime(2026, 3, 1)
        until = datetime(2026, 3, 9, 23, 59)
        result = _filter_rows_by_date(self.HEADERS, self.ROWS, since, until)
        assert len(result) == 2
        assert result[0][0] == '100'
        assert result[1][0] == '99'

    def test_no_matches(self):
        since = datetime(2026, 4, 1)
        result = _filter_rows_by_date(self.HEADERS, self.ROWS, since, None)
        assert result == []

    def test_all_match(self):
        since = datetime(2026, 1, 1)
        result = _filter_rows_by_date(self.HEADERS, self.ROWS, since, None)
        assert len(result) == 4

    def test_no_filters(self):
        result = _filter_rows_by_date(self.HEADERS, self.ROWS, None, None)
        assert len(result) == 4

    def test_unparseable_dates_skipped(self):
        rows = [
            ['101', 'Good', 'Active', '2026-03-10 14:00'],
            ['100', 'Bad date', 'Active', 'not-a-date'],
        ]
        since = datetime(2026, 3, 1)
        result = _filter_rows_by_date(self.HEADERS, rows, since, None)
        assert len(result) == 1
        assert result[0][0] == '101'
