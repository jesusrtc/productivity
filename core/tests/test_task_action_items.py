"""Dated action items retain their exact source and task/tab ownership."""
import pytest
from lab import task_checklists as checklists, objectives
from .test_objectives import objective_workspace, apply  # noqa: F401
from .test_task_cycles import write_objective_body, config


@pytest.mark.parametrize('prefix,due,label', [
    ('[2050-01-03 09:15] Review report', '2050-01-03T09:15', 'Review report'),
    ('[2050-01-03] Review report', '2050-01-03', 'Review report'),
    ('[2050-02-30 09:15] Review report', None, '[2050-02-30 09:15] Review report'),
    ('[2050-01-03 24:00] Review report', None, '[2050-01-03 24:00] Review report'),
    ('[reference] Review report', None, '[reference] Review report'),
])
def test_action_deadline_is_optional_and_validated(prefix, due, label):
    body = '# Actions\r\n\r\n  - [ ] '+prefix+'\r\n'
    item = checklists.items(body)[0]
    assert item['line'] == 3 and item['source'] == '  - [ ] '+prefix
    assert item['due'] == due and item['label'] == label and item['title'] == prefix
    assert checklists.reset(body) == body


def test_objective_actions_stay_in_their_own_tabs_and_ignore_examples(monorepo, objective_workspace):
    _, oid = objective_workspace
    data = apply(monorepo, oid, 'task', title='Review')
    parent = data['objectives'][0]['tasks'][0]
    data = apply(monorepo, oid, 'task', title='Evidence', parent_id=parent['id'])
    child = data['objectives'][0]['tasks'][0]['children'][0]
    write_objective_body(monorepo, oid, parent, '- [ ] [2050-01-03 09:00] Parent action\n- [x] Done\n')
    write_objective_body(monorepo, oid, child, '```md\n- [ ] Example\n```\n\n<details>\n<summary>Actions</summary>\n\n- [ ] Child action\n\n</details>\n')
    task = objectives.payload(monorepo, 'demo')['objectives'][0]['tasks'][0]
    assert [item['label'] for item in task['action_items']] == ['Parent action', 'Done']
    assert task['checklist'] == {'total':2, 'done':1, 'pending':1}
    assert [item['label'] for item in task['children'][0]['action_items']] == ['Child action']
    assert task['children'][0]['action_items'][0]['line'] == 8


def test_waiting_cycle_remains_hidden_until_exact_reactivation_and_resets_actions(monorepo, objective_workspace):
    from datetime import timedelta
    from lab import task_cycles
    _, oid = objective_workspace
    task = apply(monorepo, oid, 'task', title='Repeated', due='2050-01-01', recurrence=config())['objectives'][0]['tasks'][0]
    write_objective_body(monorepo, oid, task, '- [x] [2050-01-01 12:00] Verified\n')
    apply(monorepo, oid, 'task-update', task_id=task['id'], done=True)
    saved = objectives.payload(monorepo, 'demo')['objectives'][0]['tasks'][0]
    assert saved['recurrence_state']['waiting'] and saved['action_items'][0]['done']
    wake = task_cycles.activation_at(saved)
    assert not objectives.refresh_recurring(monorepo, 'demo', now=wake-timedelta(microseconds=1))
    assert objectives.refresh_recurring(monorepo, 'demo', now=wake)
    reopened = objectives.payload(monorepo, 'demo')['objectives'][0]['tasks'][0]
    assert reopened['id'] == saved['id'] and not reopened['done']
    assert not reopened['recurrence_state']['waiting'] and not reopened['action_items'][0]['done']
