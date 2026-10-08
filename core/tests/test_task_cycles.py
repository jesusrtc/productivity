"""Calendar schedules and required Markdown action items share the task lifecycle."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from lab import assistant_documents as documents, assistant_records as records, assistant_tasks
from lab import objectives, task_cycles as cycles, task_checklists as checklists
from .test_objectives import objective_workspace, apply  # noqa: F401
from .test_assistant_document_tasks import owned_tasks, legacy_tasks  # noqa: F401


def config(unit='week', every=1, lead=1440, zone='UTC', clock='12:00'):
    return {'unit':unit, 'every':every, 'reactivate_before_minutes':lead, 'timezone':zone, 'time':clock}


@pytest.mark.parametrize('due,unit,every,following', [
    ('2050-01-31','month',1,'2050-02-28'), ('2050-02-28','month',1,'2050-03-31'),
    ('2028-02-29','year',1,'2029-02-28'), ('2031-02-28','year',1,'2032-02-29'),
    ('2050-01-01','day',3,'2050-01-04'), ('2050-01-01','week',2,'2050-01-15'),
])
def test_calendar_anchor(due,unit,every,following):
    task = {'due':due,'recurrence_anchor':'2028-02-29' if unit == 'year' else '2050-01-31','recurrence':config(unit,every)}
    assert cycles.next_due(task) == following


def test_wall_clock_deadline_survives_dst_and_window_has_an_exact_boundary():
    task = {'due':'2026-03-07','recurrence':config('day',lead=60,zone='America/Los_Angeles',clock='09:00')}
    cycles.completed(task)
    wake = cycles.activation_at(task)
    assert wake == datetime(2026,3,8,15,tzinfo=timezone.utc)
    assert cycles.due_at(task,task['recurrence_next_due']) == datetime(2026,3,8,16,tzinfo=timezone.utc)
    assert not cycles.ready(task,now=wake-timedelta(microseconds=1))
    assert cycles.ready(task,now=wake)
    before = deepcopy(task)
    cycles.completed(task)
    cycles.configure(task,{'due':task['due'],'recurrence':task['recurrence']},before)
    assert task == before


@pytest.mark.parametrize('patch', [{'unit':[]},{'every':True},{'every':0},{'reactivate_before_minutes':-1},
    {'reactivate_before_minutes':1.5},{'time':'24:00'},{'timezone':'Missing/Place'},{'extra':True}])
def test_invalid_config(patch):
    with pytest.raises(ValueError):
        cycles.validate(config() | patch, '2050-01-01')


def test_markdown_counts_and_reset_preserve_real_items_and_examples():
    body = ('# Required actions\r\n\r\n- [x] Verify evidence\r\n  - [ ] Review result\r\n'
            '1. [X] Send approved result\r\n\r\n```md\r\n- [ ] Example\r\n```\r\n'
            '\r\n    - [ ] Indented example\r\n\r\n<!--\r\n- [ ] Comment\r\n-->\r\n'
            '<pre>\r\n- [x] Raw example\r\n</pre>\r\n> - [ ] Quoted example\r\n')
    assert checklists.counts(body) == {'total':3,'done':2,'pending':1}
    assert checklists.reset(body) == body.replace('[x] Verify','[ ] Verify').replace('[X] Send','[ ] Send')
    assert checklists.counts(checklists.reset(body)) == {'total':3,'done':0,'pending':3}


def write_objective_body(root, oid, task, body):
    data = objectives.payload(root,'demo')['objectives'][0]
    resource = next(row for row in data['resources'] if row['id'] == task['document_id'])
    return apply(root,oid,'document',resource_id=resource['id'],tab_id=task['tab_id'],
                 document_revision=resource['content']['revision'],body=body)


def test_objective_required_items_gate_completion_then_reopen_same_branch(monorepo, objective_workspace):
    folder, oid = objective_workspace
    data = apply(monorepo,oid,'task',title='Weekly review',due='2050-01-01',recurrence=config())
    task = data['objectives'][0]['tasks'][0]
    data = apply(monorepo,oid,'task',title='Evidence',parent_id=task['id'])
    child = data['objectives'][0]['tasks'][0]['children'][0]
    write_objective_body(monorepo,oid,task,'- [ ] Review report\n- [x] Verify source\n')
    write_objective_body(monorepo,oid,child,'- [ ] Check evidence\n')
    before = Path(data['objectives'][0]['manifest_path']).read_bytes()
    with pytest.raises(ValueError,match='pending action item'):
        apply(monorepo,oid,'task-update',task_id=task['id'],done=True)
    assert Path(data['objectives'][0]['manifest_path']).read_bytes() == before
    write_objective_body(monorepo,oid,task,'- [x] Review report\n- [x] Verify source\n')
    write_objective_body(monorepo,oid,child,'- [x] Check evidence\n')
    data = apply(monorepo,oid,'task-update',task_id=task['id'],done=True)
    saved = data['objectives'][0]['tasks'][0]
    assert saved['checklist'] == {'total':2,'done':2,'pending':0}
    assert saved['recurrence_next_due'] == '2050-01-08' and saved['due'] == '2050-01-01'
    wake = cycles.activation_at(saved)
    assert not objectives.refresh_recurring(monorepo,'demo',now=wake-timedelta(seconds=1))
    assert objectives.refresh_recurring(monorepo,'demo',now=wake)
    data = objectives.payload(monorepo,'demo')
    reopened = data['objectives'][0]['tasks'][0]
    assert reopened['id'] == task['id'] and reopened['due'] == '2050-01-08' and reopened['status'] == 'todo'
    assert reopened['children'][0]['id'] == child['id'] and reopened['children'][0]['status'] == 'todo'
    assert reopened['checklist']['pending'] == 2 and reopened['children'][0]['checklist']['pending'] == 1
    assert not data['terminal_links']
    raw = Path(data['objectives'][0]['manifest_path']).read_text()
    assert 'checklist' not in raw and 'recurrence_state' not in raw
    assert not objectives.refresh_recurring(monorepo,'demo',now=wake+timedelta(days=90))
    assert objectives.payload(monorepo,'demo')['objectives'][0]['tasks'][0]['due'] == '2050-01-08'


def test_monthly_undo_and_same_value_edits_preserve_anchor(monorepo, objective_workspace):
    _, oid = objective_workspace
    data = apply(monorepo,oid,'task',title='Monthly',due='2050-01-31',recurrence=config('month'))
    task = data['objectives'][0]['tasks'][0]
    done = apply(monorepo,oid,'task-update',task_id=task['id'],done=True)['objectives'][0]['tasks'][0]
    objectives.refresh_recurring(monorepo,'demo',now=cycles.activation_at(done))
    task = objectives.load(monorepo,'demo')['objectives'][0]['tasks'][0]
    task = apply(monorepo,oid,'task-update',task_id=task['id'],title='Renamed',due=task['due'],recurrence=task['recurrence'])['objectives'][0]['tasks'][0]
    assert task['recurrence_anchor'] == '2050-01-31'
    done = apply(monorepo,oid,'task-update',task_id=task['id'],done=True)['objectives'][0]['tasks'][0]
    assert done['recurrence_next_due'] == '2050-03-31'
    done = apply(monorepo,oid,'task-update',task_id=task['id'],recurrence=config('month',lead=60))['objectives'][0]['tasks'][0]
    assert done['recurrence_next_due'] == '2050-03-31' and done['recurrence_anchor'] == '2050-01-31'
    undo = apply(monorepo,oid,'task-update',task_id=task['id'],done=False)['objectives'][0]['tasks'][0]
    assert undo['due'] == '2050-02-28' and 'recurrence_next_due' not in undo


def test_assistant_counts_gate_api_and_recurring_reset_preserves_siblings(client,owned_tasks):
    root, note, *_ = owned_tasks
    tab = records.create_subtab(root,'Recurring actions',parent={'type':'note','id':note.stem})
    tab_id = records.resolve(root,str(tab.relative_to(root)))[1]['id']
    records.update_body(root,str(tab.relative_to(root)),'- [ ] Review report\n- [x] Verify source\n',expected='')
    result = assistant_tasks.change(root,note.stem,{'title':'Daily check','tab_id':tab_id,'due':'2050-01-01','recurrence':config('day',lead=60)})
    task_id = result['task_id']
    task = next(row for row in result['tasks'] if row['id'] == task_id)
    assert task['checklist'] == {'total':2,'done':1,'pending':1}
    before = note.read_bytes()
    response = client.post('/api/assistant/document-task',json={'document_id':note.stem,'task_id':task_id,'expected':result['revision'],'values':{'done':True}})
    assert response.status_code == 400 and 'pending action item' in response.text
    assert note.read_bytes() == before
    records.update_body(root,str(tab.relative_to(root)),'- [x] Review report\n- [x] Verify source\n',expected='- [ ] Review report\n- [x] Verify source\n')
    result = assistant_tasks.change(root,note.stem,{'done':True},task_id=task_id)
    task = next(row for row in result['tasks'] if row['id'] == task_id)
    old_meta, old_body, old_tabs = documents.unpack(note.read_bytes())
    wake = cycles.activation_at(task)
    assert not assistant_tasks.refresh_recurring(root,note.stem,now=wake-timedelta(seconds=1))
    assert assistant_tasks.refresh_recurring(root,note.stem,now=wake)
    result = assistant_tasks.view(root,note.stem)
    reopened = next(row for row in result['tasks'] if row['id'] == task_id)
    assert reopened['status'] == 'not_started' and reopened['due'] == '2050-01-02'
    assert reopened['checklist'] == {'total':2,'done':0,'pending':2}
    meta, body, tabs = documents.unpack(note.read_bytes())
    assert body == old_body and [(m,b) for m,b in tabs if m['id'] != tab_id] == [(m,b) for m,b in old_tabs if m['id'] != tab_id]
    assert {row['id'] for row in meta['tasks']} == {row['id'] for row in old_meta['tasks']}
    listing = client.get('/api/assistant').json()
    row = next(row for row in listing['documents'] if row['id'] == note.stem)
    assert next(task for task in row['task_items'] if task['id'] == task_id)['checklist']['pending'] == 2


def test_pending_parent_action_items_prevent_automatic_rollup(owned_tasks):
    root,note,*_ = owned_tasks
    tab = records.create_subtab(root,'Parent actions',parent={'type':'note','id':note.stem})
    tab_id = records.resolve(root,str(tab.relative_to(root)))[1]['id']
    records.update_body(root,str(tab.relative_to(root)),'- [ ] Parent review\n',expected='')
    data = assistant_tasks.change(root,note.stem,{'title':'Parent review','tab_id':tab_id})
    parent = data['task_id']
    data = assistant_tasks.change(root,note.stem,{'title':'Child work','parent_id':parent})
    data = assistant_tasks.change(root,note.stem,{'done':True},task_id=data['task_id'])
    task = next(row for row in data['tasks'] if row['id'] == parent)
    assert task['status'] == 'in_progress' and not task['done'] and task['checklist']['pending'] == 1
    child = next(row for row in data['tasks'] if row.get('parent_id') == parent)
    assert child['done'] and child['checklist']['total'] == 0


def test_schedule_rejects_nested_or_ambiguous_reset_ownership(monorepo,objective_workspace,owned_tasks):
    _,oid = objective_workspace
    data = apply(monorepo,oid,'task',title='Parent',due='2050-01-01',recurrence=config())
    parent = data['objectives'][0]['tasks'][0]
    before = objectives.load(monorepo,'demo')
    with pytest.raises(ValueError,match='parent task or its subtasks'):
        apply(monorepo,oid,'task',title='Child',parent_id=parent['id'],due='2050-01-01',recurrence=config())
    assert objectives.load(monorepo,'demo') == before
    root,note,*_ = owned_tasks
    # Migrated tasks already share this document's root tab. A new independent
    # schedule may not reset their action items.
    with pytest.raises(ValueError,match='tabs used only'):
        assistant_tasks.change(root,note.stem,{'title':'Shared schedule','tab_id':note.stem,'due':'2050-01-01','recurrence':config()})


def test_background_scheduler_reopens_without_a_browser_and_keeps_terminal_links(monkeypatch,monorepo,objective_workspace,owned_tasks):
    from core import task_schedule
    _,oid = objective_workspace
    root,note,*_ = owned_tasks
    task = apply(monorepo,oid,'task',title='Scheduled',due='2050-01-01',recurrence=config('day',lead=60))['objectives'][0]['tasks'][0]
    apply(monorepo,oid,'terminal',session_id='existing-session',task_id=task['id'])
    done = apply(monorepo,oid,'task-update',task_id=task['id'],done=True)['objectives'][0]['tasks'][0]
    data = assistant_tasks.change(root,note.stem,{'title':'Unlinked recurring reminder','due':'2050-01-01','recurrence':config('day',lead=60)})
    identifier = data['task_id']
    assistant_tasks.change(root,note.stem,{'done':True},task_id=identifier)
    wake = cycles.activation_at(done)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            return wake.astimezone(tz or timezone.utc)
    monkeypatch.setattr(cycles,'datetime',Clock)
    task_schedule.reconcile([monorepo],root)
    # Read the manifest directly, avoiding the read-path reconciliation.
    from lab import storage
    persisted = storage.read_json(Path(objectives.directory(monorepo,'demo')/'objectives'/oid/'.objective.json'))
    assert persisted['tasks'][0]['status'] == 'todo' and persisted['tasks'][0]['due'] == '2050-01-02'
    _,_,meta,_,_ = assistant_tasks.read(root,note.stem)
    restored = next(item for item in meta['tasks'] if item['id'] == identifier)
    assert restored['status'] == 'not_started' and restored['due'] == '2050-01-02'
    links = objectives.load(monorepo,'demo')['terminal_links']
    assert list(links) == ['existing-session'] and links['existing-session']['task_id'] == task['id']


def test_invalid_objective_schedule_leaves_files_unchanged(monorepo,objective_workspace):
    folder,oid = objective_workspace
    task = apply(monorepo,oid,'task',title='Keep',due='2050-01-01')['objectives'][0]['tasks'][0]
    originals = {file:file.read_bytes() for file in (folder/'objectives').rglob('*') if file.is_file()}
    for patch in [config()|{'unit':[]},config()|{'every':0},'weekly',True,config()|{'time':'25:00'}]:
        with pytest.raises(ValueError):
            apply(monorepo,oid,'task-update',task_id=task['id'],recurrence=patch)
        assert originals == {file:file.read_bytes() for file in originals}
    with pytest.raises(ValueError,match='due date'):
        apply(monorepo,oid,'task',title='No known deadline',recurrence=config())
    assert originals == {file:file.read_bytes() for file in originals}
