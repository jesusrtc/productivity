from datetime import datetime

import click

from trustimircli import client
from trustimircli.parser import (
    parse_list_table, parse_detail_table, parse_undo_form,
    parse_message, parse_error, parse_edit_form,
)
from trustimircli.formatter import (
    format_table, format_detail, format_message,
    format_pagination, print_undo_hint, print_error,
)
from trustimircli.undo import save_undo
from trustimircli.completions.enums import INCIDENT_STATUS, SEVERITY_LEVEL

from trustimircli.commands.comment import comment
from trustimircli.commands.timeline import timeline


@click.group('incident')
def incident():
    """Manage incidents."""
    pass


incident.add_command(comment)
incident.add_command(timeline)


@incident.command('list')
@click.option('--page', default=1, type=int, help='Page number.')
@click.option('--per-page', default=50, type=int, help='Results per page.')
@click.option('--since', default=None, help='Show incidents from this date (YYYY-MM-DD or YYYY-MM-DD HH:MM).')
@click.option('--until', default=None, help='Show incidents up to this date (YYYY-MM-DD or YYYY-MM-DD HH:MM).')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def incident_list(page, per_page, since, until, json_output):
    """List incidents. Use --since/--until to filter by date range."""
    since_dt = _parse_date(since, 'since') if since else None
    until_dt = _parse_date(until, 'until') if until else None

    resp = client.get('/html/incidents', params={'page': page, 'per_page': per_page})
    headers, rows, pagination = parse_list_table(resp.text)

    if since_dt or until_dt:
        filtered = _filter_rows_by_date(headers, rows, since_dt, until_dt)
        format_table(headers, filtered, json_output=json_output)
        if not json_output:
            click.echo(click.style(f'Showing {len(filtered)} of {len(rows)} incidents on this page (filtered by date)', dim=True))
            format_pagination(pagination)
    else:
        format_table(headers, rows, json_output=json_output)
        if not json_output:
            format_pagination(pagination)


@incident.command('view')
@click.argument('incident_id', type=int)
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def incident_view(incident_id, json_output):
    """View incident details."""
    resp = client.get(f'/html/incidents/{incident_id}')
    title, fields, sections = parse_detail_table(resp.text)
    format_detail(title, fields, sections, json_output=json_output)


@incident.command('edit')
@click.argument('incident_id', type=int)
@click.option('--title', 'opt_title', default=None, help='Incident title.')
@click.option('--desc', default=None, help='Description.')
@click.option('--status', 'opt_status', default=None,
              type=click.Choice(INCIDENT_STATUS, case_sensitive=False), help='Status.')
@click.option('--owner', default=None, help='Owner LDAP.')
@click.option('--pre-triage-sev', default=None,
              type=click.Choice(SEVERITY_LEVEL, case_sensitive=False), help='Pre-triage severity.')
@click.option('--post-triage-sev', default=None,
              type=click.Choice(SEVERITY_LEVEL, case_sensitive=False), help='Post-triage severity.')
@click.option('--started-at', default=None, help='Incident started at (YYYY-MM-DDTHH:MM).')
@click.option('--detected-at', default=None, help='Incident detected at (YYYY-MM-DDTHH:MM).')
@click.option('--first-response-at', default=None, help='First response at (YYYY-MM-DDTHH:MM).')
@click.option('--finished-at', default=None, help='Incident finished at (YYYY-MM-DDTHH:MM).')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def incident_edit(incident_id, opt_title, desc, opt_status, owner, pre_triage_sev,
                  post_triage_sev, started_at, detected_at, first_response_at,
                  finished_at, json_output):
    """Edit an incident. Interactive if no flags provided."""
    provided = {
        'title': opt_title,
        'desc': desc,
        'status': opt_status,
        'owner': owner,
        'pre_triage_sev_level': pre_triage_sev,
        'post_triage_sev_level': post_triage_sev,
        'incident_started_at': started_at,
        'incident_detected_at': detected_at,
        'incident_first_response_at': first_response_at,
        'incident_finished_at': finished_at,
    }

    any_provided = any(v is not None for v in provided.values())

    if not any_provided:
        resp = client.get(f'/html/incidents/{incident_id}/edit')
        current = parse_edit_form(resp.text)
        if not current:
            print_error('Could not parse edit form.')
            raise SystemExit(1)

        form_data = _interactive_incident_edit(current)
        if not form_data:
            click.echo('No changes.')
            return
    else:
        form_data = {k: v for k, v in provided.items() if v is not None}

    resp = client.post(f'/html/incidents/{incident_id}/edit', data=form_data)
    _handle_write_response(resp, json_output)


_DATE_FORMATS = ['%Y-%m-%d %H:%M', '%Y-%m-%d']
_DATE_COLUMN_NAMES = {'created', 'started', 'started at', 'date', 'time', 'detected', 'finished'}


def _parse_date(value, flag_name):
    """Parse a date string from CLI input."""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise click.BadParameter(
        f'Invalid date format for --{flag_name}: {value!r}. Use YYYY-MM-DD or YYYY-MM-DD HH:MM.',
        param_hint=f'--{flag_name}',
    )


def _find_date_column(headers):
    """Find the index of the date column in headers."""
    for i, h in enumerate(headers):
        if h.lower() in _DATE_COLUMN_NAMES:
            return i
    # Fallback: last column is often the date
    if headers:
        return len(headers) - 1
    return None


def _filter_rows_by_date(headers, rows, since_dt, until_dt):
    """Filter rows by date range using the date column."""
    col_idx = _find_date_column(headers)
    if col_idx is None:
        return rows

    filtered = []
    for row in rows:
        if col_idx >= len(row):
            continue
        cell = row[col_idx].strip()
        row_dt = None
        for fmt in _DATE_FORMATS:
            try:
                row_dt = datetime.strptime(cell, fmt)
                break
            except ValueError:
                continue
        if row_dt is None:
            continue
        if since_dt and row_dt < since_dt:
            continue
        if until_dt and row_dt > until_dt:
            continue
        filtered.append(row)
    return filtered


def _interactive_incident_edit(current):
    """Prompt for each editable field. Returns only changed fields."""
    fields = {}
    text_fields = ['title', 'desc', 'owner']
    enum_fields = {
        'status': INCIDENT_STATUS,
        'pre_triage_sev_level': SEVERITY_LEVEL,
        'post_triage_sev_level': SEVERITY_LEVEL,
    }
    dt_fields = [
        'incident_started_at', 'incident_detected_at',
        'incident_first_response_at', 'incident_finished_at',
    ]

    for field in text_fields:
        cur = current.get(field, '')
        new_val = click.prompt(f'{field}', default=cur, show_default=True)
        if new_val != cur:
            fields[field] = new_val

    for field, choices in enum_fields.items():
        cur = current.get(field, '')
        click.echo(f'{field} [{cur}] (choices: {", ".join(choices)})')
        new_val = click.prompt(f'{field}', default=cur, show_default=False)
        if new_val != cur:
            fields[field] = new_val

    for field in dt_fields:
        cur = current.get(field, '')
        new_val = click.prompt(f'{field} (YYYY-MM-DDTHH:MM)', default=cur, show_default=True)
        if new_val != cur:
            fields[field] = new_val

    return fields


@incident.command('link')
@click.argument('incident_id', type=int)
@click.option('--incident-ids', required=True, help='Comma-separated incident IDs to link.')
@click.option('--primary', default=None, type=int, help='Primary incident ID.')
@click.option('--title', 'group_title', default=None, help='Group title.')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def incident_link(incident_id, incident_ids, primary, group_title, json_output):
    """Link incidents into a group."""
    data = {'incident_ids': incident_ids}
    if primary is not None:
        data['primary_incident_id'] = str(primary)
    if group_title:
        data['title'] = group_title
    resp = client.post(f'/html/incidents/{incident_id}/link', data=data)
    _handle_write_response(resp, json_output)


@incident.command('unlink')
@click.argument('incident_id', type=int)
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def incident_unlink(incident_id, json_output):
    """Remove an incident from its group."""
    resp = client.post(f'/html/incidents/{incident_id}/unlink')
    _handle_write_response(resp, json_output)


def _handle_write_response(resp, json_output):
    """Handle a write response: show result, parse undo, save undo state."""
    msg = parse_message(resp.text)
    error = parse_error(resp.text)

    if error:
        print_error(error)
        raise SystemExit(1)

    title, fields, sections = parse_detail_table(resp.text)
    format_detail(title, fields, sections, json_output=json_output)

    if msg and not json_output:
        click.echo()
        format_message(msg)

    undo = parse_undo_form(resp.text)
    if undo:
        save_undo(undo['action'], undo['fields'])
        if not json_output:
            print_undo_hint()
