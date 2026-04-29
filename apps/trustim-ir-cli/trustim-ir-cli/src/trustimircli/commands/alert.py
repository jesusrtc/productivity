
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
from trustimircli.completions.enums import (
    ALERT_STATUS, ALERT_DISMISSAL_REASON, SEVERITY_LEVEL,
    INCIDENT_TYPE, INCIDENT_AREAS_OF_IMPACT, INCIDENT_ENTITY_IMPACT,
    CASE_TYPE,
)


@click.group('alert')
def alert():
    """Manage alerts."""
    pass


@alert.command('list')
@click.option('--page', default=1, type=int, help='Page number.')
@click.option('--per-page', default=50, type=int, help='Results per page.')
@click.option('--since', default=None, help='Show alerts from this date (YYYY-MM-DD or YYYY-MM-DD HH:MM).')
@click.option('--until', default=None, help='Show alerts up to this date (YYYY-MM-DD or YYYY-MM-DD HH:MM).')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def alert_list(page, per_page, since, until, json_output):
    """List alerts. Use --since/--until to filter by date range."""
    from trustimircli.commands.incident import _parse_date, _filter_rows_by_date

    since_dt = _parse_date(since, 'since') if since else None
    until_dt = _parse_date(until, 'until') if until else None

    resp = client.get('/html/alerts', params={'page': page, 'per_page': per_page})
    headers, rows, pagination = parse_list_table(resp.text)

    if since_dt or until_dt:
        filtered = _filter_rows_by_date(headers, rows, since_dt, until_dt)
        format_table(headers, filtered, json_output=json_output)
        if not json_output:
            click.echo(click.style(f'Showing {len(filtered)} of {len(rows)} alerts on this page (filtered by date)', dim=True))
            format_pagination(pagination)
    else:
        format_table(headers, rows, json_output=json_output)
        if not json_output:
            format_pagination(pagination)


@alert.command('view')
@click.argument('alert_id', type=int)
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def alert_view(alert_id, json_output):
    """View alert details."""
    resp = client.get(f'/html/alerts/{alert_id}')
    title, fields, sections = parse_detail_table(resp.text)
    format_detail(title, fields, sections, json_output=json_output)


@alert.command('edit')
@click.argument('alert_id', type=int)
@click.option('--title', 'opt_title', default=None, help='Alert title.')
@click.option('--desc', default=None, help='Description.')
@click.option('--status', 'opt_status', default=None, type=click.Choice(ALERT_STATUS, case_sensitive=False), help='Alert status.')
@click.option('--owner', default=None, help='Owner LDAP.')
@click.option('--source', default=None, help='Alert source.')
@click.option('--pre-triage-sev', default=None, type=click.Choice(SEVERITY_LEVEL, case_sensitive=False), help='Pre-triage severity.')
@click.option('--incident-type', default=None, type=click.Choice(INCIDENT_TYPE, case_sensitive=False), help='Incident type.')
@click.option('--areas-of-impact', default=None, type=click.Choice(INCIDENT_AREAS_OF_IMPACT, case_sensitive=False), help='Areas of impact.')
@click.option('--entity-impact', default=None, type=click.Choice(INCIDENT_ENTITY_IMPACT, case_sensitive=False), help='Entity impact.')
@click.option('--service-impact', default=None, help='Service impact.')
@click.option('--note', default=None, help='Note.')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def alert_edit(alert_id, opt_title, desc, opt_status, owner, source, pre_triage_sev,
               incident_type, areas_of_impact, entity_impact, service_impact, note, json_output):
    """Edit an alert. Interactive if no flags provided."""
    # Map CLI options to form field names
    provided = {
        'title': opt_title,
        'desc': desc,
        'status': opt_status,
        'owner': owner,
        'source': source,
        'pre_triage_sev_level': pre_triage_sev,
        'incident_type': incident_type,
        'areas_of_impact': areas_of_impact,
        'entity_impact': entity_impact,
        'service_impact': service_impact,
        'note': note,
    }

    # Check if any flag was explicitly provided
    any_provided = any(v is not None for v in provided.values())

    if not any_provided:
        # Interactive mode: fetch current values and prompt
        resp = client.get(f'/html/alerts/{alert_id}/edit')
        current = parse_edit_form(resp.text)
        if not current:
            print_error('Could not parse edit form.')
            raise SystemExit(1)

        form_data = _interactive_alert_edit(current)
        if not form_data:
            click.echo('No changes.')
            return
    else:
        form_data = {k: v for k, v in provided.items() if v is not None}

    resp = client.post(f'/html/alerts/{alert_id}/edit', data=form_data)
    _handle_write_response(resp, json_output)


def _interactive_alert_edit(current):
    """Prompt user for each field with current value as default. Returns changed fields."""
    fields = {}
    text_fields = ['title', 'desc', 'owner', 'source', 'service_impact', 'note']
    enum_fields = {
        'status': ALERT_STATUS,
        'pre_triage_sev_level': SEVERITY_LEVEL,
        'incident_type': INCIDENT_TYPE,
        'areas_of_impact': INCIDENT_AREAS_OF_IMPACT,
        'entity_impact': INCIDENT_ENTITY_IMPACT,
    }

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

    return fields


@alert.command('dismiss')
@click.argument('alert_id', type=int)
@click.option('--reason', default=None, type=click.Choice(ALERT_DISMISSAL_REASON, case_sensitive=False),
              help='Dismissal reason.')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def alert_dismiss(alert_id, reason, json_output):
    """Dismiss an alert."""
    if reason is None:
        reason = click.prompt(
            'Dismissal reason',
            type=click.Choice(ALERT_DISMISSAL_REASON, case_sensitive=False),
            default='FALSE_POSITIVE',
        )
    data = {'reason': reason}
    resp = client.post(f'/html/alerts/{alert_id}/dismiss', data=data)
    _handle_write_response(resp, json_output)


@alert.command('undismiss')
@click.argument('alert_id', type=int)
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def alert_undismiss(alert_id, json_output):
    """Undismiss an alert."""
    resp = client.post(f'/html/alerts/{alert_id}/undismiss')
    _handle_write_response(resp, json_output)


@alert.command('promote')
@click.argument('alert_id', type=int)
@click.option('--case-type', default=None, type=click.Choice(CASE_TYPE, case_sensitive=False),
              help='Case type for the new incident.')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def alert_promote(alert_id, case_type, json_output):
    """Promote an alert to an incident."""
    data = {}
    if case_type:
        data['case_type'] = case_type
    resp = client.post(f'/html/alerts/{alert_id}/promote', data=data)
    _handle_write_response(resp, json_output)


@alert.command('attach')
@click.argument('alert_id', type=int)
@click.option('--incident-id', required=True, type=int, help='Incident ID to attach to.')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def alert_attach(alert_id, incident_id, json_output):
    """Attach an alert to an existing incident."""
    data = {'incident_id': str(incident_id)}
    resp = client.post(f'/html/alerts/{alert_id}/attach', data=data)
    _handle_write_response(resp, json_output)


@alert.command('detach')
@click.argument('alert_id', type=int)
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def alert_detach(alert_id, json_output):
    """Detach an alert from its incident."""
    resp = client.post(f'/html/alerts/{alert_id}/detach')
    _handle_write_response(resp, json_output)


def _handle_write_response(resp, json_output):
    """Handle a write response: show result, parse undo, save undo state."""
    msg = parse_message(resp.text)
    error = parse_error(resp.text)

    if error:
        print_error(error)
        raise SystemExit(1)

    # Show the detail view
    title, fields, sections = parse_detail_table(resp.text)
    format_detail(title, fields, sections, json_output=json_output)

    if msg and not json_output:
        click.echo()
        format_message(msg)

    # Parse and save undo
    undo = parse_undo_form(resp.text)
    if undo:
        save_undo(undo['action'], undo['fields'])
        if not json_output:
            print_undo_hint()
