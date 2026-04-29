import os

from trustimircli.parser import (
    parse_list_table, parse_detail_table, parse_undo_form,
    parse_message, parse_timeline_table,
)

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def _read(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


class TestParseListTable:
    def test_alerts_list(self):
        html = _read('alerts_list.html')
        headers, rows, pagination = parse_list_table(html)
        assert headers == ['ID', 'Title', 'Status', 'Severity', 'Type', 'Source',
                           'Owner', 'Team', 'Incident', 'Created']
        assert len(rows) == 2
        assert rows[0][0] == '101'
        assert rows[0][1] == 'Suspicious login spike'
        assert rows[0][2] == 'UNCLAIMED'
        assert rows[1][0] == '100'
        assert rows[1][8] == '50'  # incident ID from link
        assert pagination['total'] == '75'
        assert 'Page 1 of 2' in pagination['page_info']

    def test_empty_table(self):
        html = '<html><body><table><tr><th>ID</th></tr></table></body></html>'
        headers, rows, pagination = parse_list_table(html)
        assert headers == ['ID']
        assert rows == []


class TestParseDetailTable:
    def test_alert_detail(self):
        html = _read('alert_detail.html')
        title, fields, sections = parse_detail_table(html)
        assert 'Alert #101' in title
        assert ('Status', 'UNCLAIMED') in fields
        assert ('Pre-Triage Sev', 'SEV2') in fields
        assert ('Owner', 'jdoe') in fields

        # Check description section
        desc_sections = [s for s in sections if s[0] == 'Description']
        assert len(desc_sections) == 1
        assert '500+ failed login' in desc_sections[0][1][0]

    def test_no_table(self):
        html = '<html><body><h1>Title</h1></body></html>'
        title, fields, sections = parse_detail_table(html)
        assert title == 'Title'
        assert fields == []


class TestParseUndoForm:
    def test_alert_edit_undo(self):
        html = _read('alert_post_result_with_undo.html')
        undo = parse_undo_form(html)
        assert undo is not None
        assert undo['action'] == '/html/alerts/101/edit'
        assert undo['fields']['_prev_status'] == 'UNCLAIMED'
        assert undo['fields']['_expect_status'] == 'TRIAGING'

    def test_incident_edit_undo(self):
        html = _read('incident_post_result_with_undo.html')
        undo = parse_undo_form(html)
        assert undo is not None
        assert undo['action'] == '/html/incidents/50/edit'
        assert undo['fields']['status'] == ''
        assert undo['fields']['_expect_status'] == 'Active'

    def test_no_undo(self):
        html = '<html><body><p>Done.</p></body></html>'
        undo = parse_undo_form(html)
        assert undo is None


class TestParseMessage:
    def test_banner_message(self):
        html = _read('alert_post_result_with_undo.html')
        msg = parse_message(html)
        assert msg is not None
        assert 'Updated' in msg or 'status' in msg

    def test_no_message(self):
        html = '<html><body></body></html>'
        msg = parse_message(html)
        assert msg is None


class TestParseTimelineTable:
    def test_timeline_list(self):
        html = _read('timeline_list.html')
        headers, rows, title, info_msg = parse_timeline_table(html)
        assert 'Incident #50' in title
        assert 'ID' in headers
        assert 'Time' in headers
        assert 'Actions' not in headers
        assert len(rows) == 2
        assert rows[0][0] == '1'
        assert rows[0][2] == 'ALERT_ATTACH'
        assert info_msg is None
