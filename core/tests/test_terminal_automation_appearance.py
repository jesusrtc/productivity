"""Recipe appearance reaches saved/live terminals without changing commands."""
import base64
import struct
import uuid
import zlib

import pytest

from core import terminal_automations
from .test_term_routes import isolated_prefix  # noqa: F401
from .test_terminal_automations import _save, _wip_target


def launch(client, catalog, folder, **patch):
    return {**_wip_target(client), 'workspace_id': 'demo', 'cwd': str(folder), 'automation_id': 'dev',
            'revision': catalog['revision'], 'run_id': str(uuid.uuid4()), **patch}


def test_defaults_and_overrides_reach_preview_live_saved_and_restore(client, seed_workspace, monorepo, isolated_prefix):
    folder = seed_workspace()
    catalog = _save(client, 'demo', [
        {'label': 'Main', 'command': 'printf main'},
        {'label': 'Child', 'command': 'printf child'},
        {'label': 'Custom', 'command': 'printf custom', 'icon': {'emoji': '🚀'}, 'color': '#58a6ff'},
    ], launch_delay_seconds=0, icon={'service': 'github'}, color='#3fb950')
    body = launch(client, catalog, folder)
    preview = client.post('/api/term/automations/launch', json={**body, 'preview': True}).json()
    expected = [{'icon': {'service': 'github'}, 'color': '#3fb950', 'role': 'main', 'inherit_icon': False},
                {'icon': {'service': 'github'}, 'color': None, 'role': 'child', 'inherit_icon': True},
                {'icon': {'emoji': '🚀'}, 'color': '#58a6ff', 'role': 'child', 'inherit_icon': False}]
    assert [step['appearance'] for step in preview['steps']] == expected
    response = client.post('/api/term/automations/launch', json=body)
    assert response.status_code == 200, response.text
    rows = response.json()['sessions']
    assert [row['automation_appearance'] for row in rows] == expected
    saved = client.get('/api/term/sessions/saved?workspace_id=demo').json()
    assert [row['automation_appearance'] for row in saved] == expected
    from core.routes import term
    recovered = term._reconstruct_meta_entry(monorepo, rows[0]['name'], parsed=('demo', rows[0]['logical_name']))
    assert recovered['automation_appearance'] == expected[0]
    live = client.get('/api/term/sessions?workspace_id=demo').json()
    assert {row['logical_name']: row['automation_appearance'] for row in live} == {
        row['logical_name']: appearance for row, appearance in zip(rows, expected)}
    assert client.delete('/api/term/sessions/' + rows[1]['name']).status_code == 200
    restored = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal', 'name': rows[1]['logical_name']})
    assert restored.status_code == 200, restored.text
    assert restored.json()['automation_appearance'] == expected[1]
    status = client.get('/api/term/automations/status?workspace_id=demo').json()
    assert {r['logical_name']: r['automation_appearance'] for r in status['sessions']} == {
        row['logical_name']: appearance for row, appearance in zip(rows, expected)}


def test_existing_parent_keeps_name_and_children_inherit_its_recipe_icon(client, seed_workspace, isolated_prefix):
    folder = seed_workspace()
    parent = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal', 'name': 'parent', 'label': 'My main'}).json()
    catalog = _save(client, 'demo', [{'label': 'Logs', 'command': 'printf logs'}],
                    launch_delay_seconds=0, icon={'service': 'github'}, color='#ffa657')
    body = launch(client, catalog, folder, parent=parent['name'])
    body.pop('cwd')
    result = client.post('/api/term/automations/launch', json=body)
    assert result.status_code == 200, result.text
    assert result.json()['sessions'][0]['automation_appearance'] == {'icon': {'service': 'github'}, 'color': None, 'role': 'child', 'inherit_icon': True}
    saved = client.get('/api/term/sessions/saved?workspace_id=demo').json()[0]
    assert saved['label'] == 'My main'
    assert saved['automation_appearance'] == {'icon': {'service': 'github'}, 'color': '#ffa657', 'role': 'main', 'inherit_icon': False}


def test_primary_step_icon_is_inherited_by_default_children():
    recipe = terminal_automations.Automation(id='dev', name='Dev', steps=[
        {'label': 'Main', 'command': 'true', 'icon': {'emoji': '🚀'}}, {'label': 'Child', 'command': 'true'},
    ]).model_dump()
    assert terminal_automations.appearance(recipe, recipe['steps'][1], 1)['icon'] == {'emoji': '🚀'}
    assert terminal_automations.appearance(recipe, recipe['steps'][1], 1, parent=True)['icon'] == {'builtin': 'terminal'}


@pytest.mark.parametrize('patch', [
    {'icon': {'service': '<script>'}}, {'icon': {'builtin': 'anything'}}, {'icon': {'emoji': '<img>'}},
    {'icon': {'emoji': '🚀', 'service': 'github'}}, {'icon': {'image': 'data:image/svg+xml,<svg/>'}},
    {'color': 'red;display:none'}, {'color': '#fff'},
])
def test_invalid_icons_or_colors_cannot_replace_the_saved_recipe(client, seed_workspace, isolated_prefix, patch):
    seed_workspace()
    catalog = _save(client, 'demo', [{'label': 'Main', 'command': 'true'}])
    row = {**catalog['automations'][0], **patch}
    response = client.post('/api/term/automations', json={'workspace_id': 'demo', 'revision': catalog['revision'], 'automations': [row]})
    assert response.status_code == 422
    assert client.get('/api/term/automations?workspace_id=demo').json() == catalog


def test_uploaded_png_icon_round_trips_in_recipe():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff\xff')) + chunk(b'IEND', b'')
    image = 'data:image/png;base64,' + base64.b64encode(png).decode()
    row = terminal_automations.Automation(id='dev', name='Dev', icon={'image': image}, steps=[{'label': 'Main', 'command': 'true'}])
    assert row.model_dump()['icon'] == {'image': image}
