"""Calendar-anchored recurring tasks with an explicit, automatic wake window."""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UNITS = {'day', 'week', 'month', 'year'}


def validate(config, due):
    if config is None:
        return
    if not isinstance(config, dict) or set(config) - {'every', 'unit', 'time', 'timezone', 'reactivate_before_minutes'}:
        raise ValueError('Choose a repeat interval and reactivation window')
    if type(config.get('every')) is not int or not 1 <= config['every'] <= 1000 or not isinstance(config.get('unit'), str) or config['unit'] not in UNITS:
        raise ValueError('Repeat every 1–1000 days, weeks, months or years')
    minutes = config.get('reactivate_before_minutes')
    if type(minutes) is not int or not 0 <= minutes <= 525600:
        raise ValueError('Reactivation must be 0–525600 minutes before the deadline')
    try:
        if not isinstance(due, str) or date.fromisoformat(due).isoformat() != due:
            raise ValueError()
        clock = config.get('time')
        if not isinstance(clock, str) or len(clock) != 5 or time.fromisoformat(clock).strftime('%H:%M') != clock:
            raise ValueError()
        if not isinstance(config.get('timezone'), str):
            raise ValueError()
        ZoneInfo(config['timezone'])
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError('A recurring task needs a due date, deadline time and valid time zone') from exc
    try:
        next_due({'recurrence':config, 'due':due})
    except (OverflowError, ValueError) as exc:
        raise ValueError('The next deadline must fit within the calendar') from exc


def next_due(task):
    config = task['recurrence']
    due = date.fromisoformat(task['due'])
    anchor = date.fromisoformat(task.get('recurrence_anchor') or task['due'])
    every, unit = config['every'], config['unit']
    if unit in {'day', 'week'}:
        following = due + timedelta(days=every * (7 if unit == 'week' else 1))
    else:
        months = every * (12 if unit == 'year' else 1)
        total = due.year * 12 + due.month - 1 + months
        year, month = total // 12, total % 12 + 1
        following = date(year, month, min(anchor.day, monthrange(year, month)[1]))
    return following.isoformat()


def due_at(task, due=None):
    config = task['recurrence']
    # Wall-clock deadlines retain their local hour across DST. A nonexistent
    # clock time resolves forward through the gap; ambiguous times use fold=0.
    local = datetime.combine(date.fromisoformat(due or task['due']), time.fromisoformat(config['time']))
    return local.replace(tzinfo=ZoneInfo(config['timezone'])).astimezone(timezone.utc)


def activation_at(task):
    return due_at(task, task['recurrence_next_due']) - timedelta(minutes=task['recurrence']['reactivate_before_minutes'])


def configure(task, changed, previous=None):
    config = task.get('recurrence')
    if not isinstance(config, dict):
        task.pop('recurrence_next_due', None)
        return
    validate(config, task.get('due'))
    prior = (previous or {}).get('recurrence')
    deadline_changed = 'due' in changed and (previous is None or previous.get('due') != task.get('due'))
    interval_changed = 'recurrence' in changed and (not isinstance(prior, dict) or
                       any(prior.get(field) != config[field] for field in ('every','unit')))
    if deadline_changed or interval_changed:
        task['recurrence_anchor'] = task['due']
        task.pop('recurrence_next_due', None)


def completed(task):
    """Queue one next deadline; retries never advance the task twice."""
    if not isinstance(task.get('recurrence'), dict):
        return
    validate(task['recurrence'], task.get('due'))
    task.setdefault('recurrence_anchor', task['due'])
    if not task.get('recurrence_next_due'):
        task['recurrence_next_due'] = next_due(task)
        task['recurrence_last_completed'] = {'due':task['due'], 'completed_at':datetime.now(timezone.utc).isoformat()}


def reopened(task):
    task.pop('recurrence_next_due', None)


def ready(task, *, now=None):
    if not isinstance(task.get('recurrence'), dict) or not task.get('recurrence_next_due'):
        return False
    return (now or datetime.now(timezone.utc)) >= activation_at(task)


def state(task):
    if not isinstance(task.get('recurrence'), dict):
        return None
    result = {'due_at':due_at(task).isoformat(), 'waiting':bool(task.get('recurrence_next_due'))}
    if task.get('recurrence_next_due'):
        result.update(next_due=task['recurrence_next_due'], next_due_at=due_at(task,task['recurrence_next_due']).isoformat(),
                      reactivate_at=activation_at(task).isoformat())
    return result


def validate_tree(tasks):
    """One schedule owns a branch; independent schedules cannot reset each other."""
    by_id = {task['id']:task for task in tasks}
    for task in tasks:
        if not isinstance(task.get('recurrence'), dict):
            continue
        validate(task['recurrence'], task.get('due'))
        parent, seen = task.get('parent_id'), set()
        while parent and parent not in seen:
            seen.add(parent)
            ancestor = by_id.get(parent, {})
            if isinstance(ancestor.get('recurrence'), dict):
                raise ValueError('Schedule the parent task or its subtasks, not both')
            parent = ancestor.get('parent_id')
