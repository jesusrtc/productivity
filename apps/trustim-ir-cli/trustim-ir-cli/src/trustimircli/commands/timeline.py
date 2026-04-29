import click

from trustimircli import client
from trustimircli.parser import (
    parse_timeline_table, parse_undo_form, parse_message,
    parse_edit_form,
)
from trustimircli.formatter import format_table, format_message, print_undo_hint, print_error
from trustimircli.undo import save_undo
from trustimircli.completions.enums import TIMELINE_EVENT_TYPE


@click.group('timeline')
def timeline():
    """Manage incident timeline entries."""
    pass


@timeline.command('list')
@click.argument('incident_id', type=int)
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def timeline_list(incident_id, json_output):
    """List timeline entries for an incident."""
    resp = client.get(f'/html/incidents/{incident_id}/timeline')
    headers, rows, incident_title, info_msg = parse_timeline_table(resp.text)
    if info_msg:
        format_message(info_msg)
    click.echo(click.style(incident_title, bold=True))
    click.echo()
    format_table(headers, rows, json_output=json_output)


@timeline.command('add')
@click.argument('incident_id', type=int)
@click.option('--time', 'time_str', required=True, help='Event time (YYYY-MM-DDTHH:MM).')
@click.option('--event', 'timeline_event', required=True, help='Timeline event name/description.')
@click.option('--event-type', default='Milestone',
              type=click.Choice(TIMELINE_EVENT_TYPE, case_sensitive=False),
              help='Event type.')
@click.option('--old-value', default='', help='Old value.')
@click.option('--new-value', default='', help='New value.')
@click.option('--actor', default='', help='Actor (defaults to current user).')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def timeline_add(incident_id, time_str, timeline_event, event_type, old_value,
                 new_value, actor, json_output):
    """Add a timeline entry to an incident."""
    data = {
        'time': time_str,
        'timeline_event': timeline_event,
        'event_type': event_type,
    }
    if old_value:
        data['old_value'] = old_value
    if new_value:
        data['new_value'] = new_value
    if actor:
        data['actor'] = actor

    resp = client.post(f'/html/incidents/{incident_id}/timeline/add', data=data)
    _handle_timeline_response(resp, json_output)


@timeline.command('edit')
@click.argument('incident_id', type=int)
@click.argument('entry_id', type=int)
@click.option('--time', 'time_str', default=None, help='Event time (YYYY-MM-DDTHH:MM).')
@click.option('--event', 'timeline_event', default=None, help='Timeline event name.')
@click.option('--event-type', default=None,
              type=click.Choice(TIMELINE_EVENT_TYPE, case_sensitive=False),
              help='Event type.')
@click.option('--old-value', default=None, help='Old value.')
@click.option('--new-value', default=None, help='New value.')
@click.option('--actor', default=None, help='Actor.')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def timeline_edit(incident_id, entry_id, time_str, timeline_event, event_type,
                  old_value, new_value, actor, json_output):
    """Edit a timeline entry. Interactive if no flags provided."""
    provided = {
        'time': time_str,
        'timeline_event': timeline_event,
        'event_type': event_type,
        'old_value': old_value,
        'new_value': new_value,
        'actor': actor,
    }

    any_provided = any(v is not None for v in provided.values())

    if not any_provided:
        resp = client.get(f'/html/incidents/{incident_id}/timeline/{entry_id}/edit')
        current = parse_edit_form(resp.text)
        if not current:
            print_error('Could not parse edit form.')
            raise SystemExit(1)

        form_data = _interactive_timeline_edit(current)
        if not form_data:
            click.echo('No changes.')
            return
    else:
        # For non-interactive, we need all required fields; fetch current values
        # and merge with provided
        resp = client.get(f'/html/incidents/{incident_id}/timeline/{entry_id}/edit')
        current = parse_edit_form(resp.text)
        form_data = {}
        for key in ('time', 'timeline_event', 'event_type', 'old_value', 'new_value', 'actor'):
            if provided.get(key) is not None:
                form_data[key] = provided[key]
            elif key in current:
                form_data[key] = current[key]

    resp = client.post(
        f'/html/incidents/{incident_id}/timeline/{entry_id}/edit',
        data=form_data,
    )
    _handle_timeline_response(resp, json_output)


def _interactive_timeline_edit(current):
    """Prompt for each field with current value as default."""
    fields = {}
    for field in ('time', 'timeline_event', 'old_value', 'new_value', 'actor'):
        cur = current.get(field, '')
        new_val = click.prompt(f'{field}', default=cur, show_default=True)
        if new_val != cur:
            fields[field] = new_val
        else:
            fields[field] = cur  # Always send all fields for edit

    cur_type = current.get('event_type', 'Milestone')
    click.echo(f'event_type [{cur_type}] (choices: {", ".join(TIMELINE_EVENT_TYPE)})')
    new_type = click.prompt('event_type', default=cur_type, show_default=False)
    fields['event_type'] = new_type

    return fields


@timeline.command('delete')
@click.argument('incident_id', type=int)
@click.argument('entry_id', type=int)
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
@click.confirmation_option(prompt='Are you sure you want to delete this timeline entry?')
def timeline_delete(incident_id, entry_id, json_output):
    """Delete a timeline entry."""
    resp = client.post(f'/html/incidents/{incident_id}/timeline/{entry_id}/delete')
    _handle_timeline_response(resp, json_output)


def _handle_timeline_response(resp, json_output):
    """Handle a timeline write response."""
    headers, rows, incident_title, info_msg = parse_timeline_table(resp.text)

    if info_msg:
        format_message(info_msg)

    if not json_output:
        click.echo(click.style(incident_title, bold=True))
        click.echo()

    format_table(headers, rows, json_output=json_output)

    undo = parse_undo_form(resp.text)
    if undo:
        save_undo(undo['action'], undo['fields'])
        if not json_output:
            msg = parse_message(resp.text)
            if msg:
                click.echo()
                format_message(msg)
            print_undo_hint()
