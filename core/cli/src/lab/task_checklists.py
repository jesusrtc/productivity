"""Required Markdown action items. Never synthesize or rewrite their wording."""
import re
from datetime import datetime

ITEM = re.compile(r'^(?P<prefix>[ \t]*(?:[-*+]|\d+[.)])[ \t]+\[)(?P<mark>[ xX])\](?:[ \t]+(?P<title>.*))?(?:\r?\n)?$')
FENCE = re.compile(r'^[ \t]*(`{3,}|~{3,})(.*)$')
DUE = re.compile(r'^\[(\d{4}-\d{2}-\d{2})(?:[ \t]+(\d{2}:\d{2}))?\][ \t]*(.*)$')


def deadline(title):
    """Optional local wall-clock deadline; invalid prefixes remain ordinary text."""
    match = DUE.match(title)
    if match:
        due = match[1] + ('T' + match[2] if match[2] else '')
        try:
            datetime.strptime(due, '%Y-%m-%dT%H:%M' if match[2] else '%Y-%m-%d')
        except ValueError:
            pass
        else:
            return due, match[3]
    return None, title


def items(body):
    result, fence, comment, raw = [], None, False, None
    list_indents = []
    for index, line in enumerate(body.splitlines(keepends=True)):
        stripped = line.strip()
        marker = FENCE.match(line)
        if fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if comment:
            comment = '-->' not in line
            continue
        if raw:
            if re.search(r'</' + raw + r'\s*>', line, re.I):
                raw = None
            continue
        expanded = line.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(' '))
        if stripped:
            while list_indents and indent < list_indents[-1]:
                list_indents.pop()
        base = list_indents[-1] if list_indents else 0
        if indent >= base + 4:
            continue
        if marker:
            fence = marker[1]
            continue
        if re.match(r'^<(pre|script|style|textarea|code)(?:\s|>)', stripped, re.I):
            tag = re.match(r'^<(\w+)', stripped)[1].lower()
            if not re.search(r'</' + tag + r'\s*>', line, re.I):
                raw = tag
            continue
        if stripped.startswith('<!--'):
            comment = '-->' not in stripped[4:]
            continue
        # Four spaces beyond the current list's content column are code,
        # including standalone indented examples. Nested live lists remain work.
        if indent >= base + 4:
            continue
        bullet = re.match(r'^[ ]*(?:[-*+]|\d+[.)])[ ]+', expanded)
        if bullet:
            list_indents.append(len(bullet[0]))
        match = ITEM.match(line)
        if match:
            title = (match['title'] or '').strip()
            due, label = deadline(title)
            result.append({'line':index + 1, 'title':title, 'label':label, 'due':due,
                           'source':line.rstrip('\r\n'),
                           'done':match['mark'].lower() == 'x', 'column':match.start('mark')})
    return result


def counts(body):
    rows = items(body)
    done = sum(row['done'] for row in rows)
    return {'total':len(rows), 'done':done, 'pending':len(rows) - done}


def reset(body):
    """Reopen the exact existing items, retaining line endings and all text."""
    lines = body.splitlines(keepends=True)
    for row in items(body):
        if row['done']:
            index, column = row['line'] - 1, row['column']
            lines[index] = lines[index][:column] + ' ' + lines[index][column + 1:]
    return ''.join(lines)


def require_complete(body):
    pending = counts(body)['pending']
    if pending:
        raise ValueError(f'Complete the {pending} pending action item(s) in this task’s Markdown before completing the task')
