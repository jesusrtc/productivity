import json

from trustimircli.formatter import format_table, format_detail


class TestFormatTable:
    def test_basic_table(self, capsys):
        headers = ['ID', 'Name']
        rows = [['1', 'Alice'], ['2', 'Bob']]
        format_table(headers, rows)
        out = capsys.readouterr().out
        assert 'ID' in out
        assert 'Alice' in out
        assert 'Bob' in out

    def test_empty_table(self, capsys):
        format_table(['ID'], [])
        out = capsys.readouterr().out
        assert 'No results' in out

    def test_json_output(self, capsys):
        headers = ['ID', 'Name']
        rows = [['1', 'Alice']]
        format_table(headers, rows, json_output=True)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) == 1
        assert data[0]['ID'] == '1'
        assert data[0]['Name'] == 'Alice'


class TestFormatDetail:
    def test_basic_detail(self, capsys):
        format_detail(
            'Alert #101',
            [('Status', 'UNCLAIMED'), ('Owner', 'jdoe')],
            [],
        )
        out = capsys.readouterr().out
        assert 'Alert #101' in out
        assert 'UNCLAIMED' in out
        assert 'jdoe' in out

    def test_json_detail(self, capsys):
        format_detail(
            'Alert #101',
            [('Status', 'UNCLAIMED')],
            [('Description', ['some text'])],
            json_output=True,
        )
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data['title'] == 'Alert #101'
        assert data['Status'] == 'UNCLAIMED'
        assert data['Description'] == ['some text']

    def test_detail_with_sub_table(self, capsys):
        format_detail(
            'Incident #50',
            [('Status', 'Active')],
            [('Alerts', [{'headers': ['ID', 'Title'], 'rows': [['100', 'Test']]}])],
        )
        out = capsys.readouterr().out
        assert 'Incident #50' in out
        assert 'Active' in out
        assert 'Test' in out
