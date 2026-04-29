import click

from trustimircli import client
from trustimircli.parser import (
    parse_detail_table, parse_undo_form, parse_message, parse_error,
)
from trustimircli.formatter import (
    format_detail, format_message, print_undo_hint, print_error,
)
from trustimircli.undo import save_undo


@click.group('comment')
def comment():
    """Manage incident comments."""
    pass


@comment.command('add')
@click.argument('incident_id', type=int)
@click.option('--content', default=None, help='Comment content.')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def comment_add(incident_id, content, json_output):
    """Add a comment to an incident."""
    if content is None:
        content = click.prompt('Comment content')
    if not content.strip():
        print_error('Content is required.')
        raise SystemExit(1)

    data = {'content': content}
    resp = client.post(f'/html/incidents/{incident_id}/comment', data=data)
    _handle_write_response(resp, json_output)


@comment.command('edit')
@click.argument('incident_id', type=int)
@click.argument('comment_id', type=int)
@click.option('--content', default=None, help='New comment content.')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
def comment_edit(incident_id, comment_id, content, json_output):
    """Edit a comment on an incident."""
    if content is None:
        # Fetch current content for interactive editing
        resp = client.get(f'/html/incidents/{incident_id}/comment/{comment_id}/edit')
        from trustimircli.parser import parse_edit_form
        current = parse_edit_form(resp.text)
        current_content = current.get('content', '')
        content = click.prompt('Content', default=current_content, show_default=True)

    if not content.strip():
        print_error('Content is required.')
        raise SystemExit(1)

    data = {'content': content}
    resp = client.post(f'/html/incidents/{incident_id}/comment/{comment_id}/edit', data=data)
    _handle_write_response(resp, json_output)


@comment.command('delete')
@click.argument('incident_id', type=int)
@click.argument('comment_id', type=int)
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON.')
@click.confirmation_option(prompt='Are you sure you want to delete this comment?')
def comment_delete(incident_id, comment_id, json_output):
    """Delete a comment from an incident."""
    resp = client.post(f'/html/incidents/{incident_id}/comment/{comment_id}/delete')
    _handle_write_response(resp, json_output)


def _handle_write_response(resp, json_output):
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
