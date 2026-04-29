from bs4 import BeautifulSoup


def parse_html(html):
    return BeautifulSoup(html, 'html.parser')


def parse_list_table(html):
    """Parse a list page with a <table> containing <th> headers and <tr> rows.
    Returns (headers, rows, pagination_info).
    """
    soup = parse_html(html)

    # Extract pagination info from the <p> tag like "Total: 42 | Page 1 of 3 | Per page: 50"
    pagination = {}
    for p in soup.find_all('p'):
        text = p.get_text()
        if 'Total:' in text and 'Page' in text:
            parts = text.split('|')
            for part in parts:
                part = part.strip()
                if part.startswith('Total:'):
                    pagination['total'] = part.split(':')[1].strip()
                elif part.startswith('Page'):
                    pagination['page_info'] = part.strip()
                elif part.startswith('Per page:'):
                    pagination['per_page'] = part.split(':')[1].strip()
            break

    table = soup.find('table')
    if not table:
        return [], [], pagination

    headers = []
    header_row = table.find('tr')
    if header_row:
        for th in header_row.find_all('th'):
            headers.append(th.get_text(strip=True))

    rows = []
    for tr in table.find_all('tr')[1:]:  # skip header row
        cells = tr.find_all('td')
        row = []
        for cell in cells:
            # Prefer link text for ID columns
            link = cell.find('a')
            if link:
                row.append(link.get_text(strip=True))
            else:
                row.append(cell.get_text(strip=True))
        if row:
            rows.append(row)

    return headers, rows, pagination


def parse_detail_table(html):
    """Parse a detail page with key-value <table> rows (<th>key</th><td>value</td>).
    Returns (title, fields, sections) where fields is a list of (key, value) tuples
    and sections is a list of (heading, content) tuples.
    """
    soup = parse_html(html)

    # Extract title from <h1>
    h1 = soup.find('h1')
    title = h1.get_text(strip=True) if h1 else ''

    # Extract key-value pairs from the first table
    fields = []
    table = soup.find('table')
    if table:
        for tr in table.find_all('tr'):
            th = tr.find('th')
            td = tr.find('td')
            if th and td:
                key = th.get_text(strip=True)
                # Check for links in value
                link = td.find('a')
                if link:
                    val = link.get_text(strip=True)
                else:
                    val = td.get_text(strip=True)
                fields.append((key, val))

    # Extract sections (h2 + content)
    sections = []
    for h2 in soup.find_all('h2'):
        heading = h2.get_text(strip=True)
        # Content is in <pre> or a <table> after the h2
        content_parts = []
        sibling = h2.find_next_sibling()
        while sibling and sibling.name != 'h2':
            if sibling.name == 'pre':
                content_parts.append(sibling.get_text())
            elif sibling.name == 'table':
                # Sub-table (alerts, comments, docs, etc.)
                sub_headers = []
                sub_rows = []
                first_tr = sibling.find('tr')
                if first_tr:
                    sub_headers = [th.get_text(strip=True) for th in first_tr.find_all('th')]
                for tr in sibling.find_all('tr')[1:]:
                    cells = tr.find_all('td')
                    row = []
                    for cell in cells:
                        link = cell.find('a')
                        row.append(link.get_text(strip=True) if link else cell.get_text(strip=True))
                    if row:
                        sub_rows.append(row)
                if sub_headers or sub_rows:
                    content_parts.append({'headers': sub_headers, 'rows': sub_rows})
            elif sibling.name == 'hr':
                pass  # skip
            elif sibling.name == 'p':
                # Comments appear as <p><strong>author</strong> - date ...</p><pre>content</pre>
                text = sibling.get_text(strip=True)
                if text:
                    content_parts.append(text)
            sibling = sibling.find_next_sibling()

        sections.append((heading, content_parts))

    return title, fields, sections


def parse_undo_form(html):
    """Parse undo form data from a response page.
    Looks for <form> with hidden inputs containing _prev_, _expect_, _undo, or _undo_comment_id fields.

    Returns dict with 'action' (form URL) and 'fields' (dict of hidden field name->value),
    or None if no undo form found.
    """
    soup = parse_html(html)

    for form in soup.find_all('form', method=True):
        if form.get('method', '').upper() != 'POST':
            continue
        hidden_inputs = form.find_all('input', type='hidden')
        if not hidden_inputs:
            continue
        # Check if this looks like an undo form (has hidden fields with _prev_, _expect_, _undo, etc.)
        field_names = [inp.get('name', '') for inp in hidden_inputs]
        undo_names = (
            '_undo', '_undo_comment_id', '_undo_entry_id',
            '_was_new_group', '_prev_group_id', '_group_was_deleted',
            'reason',
        )
        is_undo = any(
            n.startswith('_prev_') or n.startswith('_expect_') or
            n in undo_names
            for n in field_names
        )
        # Also check for a button that says "Undo"
        button = form.find('button')
        has_undo_button = button and 'undo' in button.get_text(strip=True).lower()

        if is_undo or has_undo_button:
            action = form.get('action', '')
            fields = {}
            for inp in hidden_inputs:
                name = inp.get('name', '')
                value = inp.get('value', '')
                if name:
                    fields[name] = value
            return {'action': action, 'fields': fields}

    return None


def parse_message(html):
    """Parse a message/error from a response page.
    Looks for <p><strong>message</strong></p> pattern or undo_message divs.
    """
    soup = parse_html(html)

    # Check for undo banner summary
    for div in soup.find_all('div'):
        p = div.find('p')
        if p:
            form = p.find('form')
            if form:
                # Remove the form to get just the message text
                form_text = form.get_text()
                full_text = p.get_text()
                msg = full_text.replace(form_text, '').strip().rstrip('.')
                if msg:
                    return msg

    # Check for simple message pattern
    for p in soup.find_all('p'):
        strong = p.find('strong')
        if strong and not p.find('form'):
            return strong.get_text(strip=True)

    return None


def parse_error(html):
    """Parse error message from response HTML."""
    soup = parse_html(html)
    for p in soup.find_all('p'):
        strong = p.find('strong')
        if strong and 'error' in strong.get_text(strip=True).lower():
            return p.get_text(strip=True).replace('Error:', '').strip()
    return None


def parse_edit_form(html):
    """Parse an edit form to get current field values (for interactive mode).
    Returns dict of field_name -> current_value.
    """
    soup = parse_html(html)
    form = soup.find('form', method='POST')
    if not form:
        return {}

    fields = {}

    # Text inputs
    for inp in form.find_all('input', type='text'):
        name = inp.get('name', '')
        if name:
            fields[name] = inp.get('value', '')

    # Datetime-local inputs
    for inp in form.find_all('input', attrs={'type': 'datetime-local'}):
        name = inp.get('name', '')
        if name:
            fields[name] = inp.get('value', '')

    # Textareas
    for ta in form.find_all('textarea'):
        name = ta.get('name', '')
        if name:
            fields[name] = ta.get_text()

    # Selects (get selected option)
    for select in form.find_all('select'):
        name = select.get('name', '')
        if name:
            selected = select.find('option', selected=True)
            if selected:
                fields[name] = selected.get('value', '')
            else:
                fields[name] = ''

    return fields


def parse_timeline_table(html):
    """Parse the timeline list page. Returns (headers, rows, incident_title)."""
    soup = parse_html(html)
    h1 = soup.find('h1')
    incident_title = h1.get_text(strip=True) if h1 else ''

    # Check for info_message
    info_msg = None
    for div in soup.find_all('div'):
        p = div.find('p')
        if p and not p.find('form'):
            text = p.get_text(strip=True)
            if text and ('Undo' in text or 'Nothing' in text):
                info_msg = text

    table = soup.find('table')
    if not table:
        return [], [], incident_title, info_msg

    headers = []
    first_tr = table.find('tr')
    if first_tr:
        headers = [th.get_text(strip=True) for th in first_tr.find_all('th')]

    rows = []
    for tr in table.find_all('tr')[1:]:
        cells = tr.find_all('td')
        row = []
        for cell in cells:
            # Skip the Actions column (contains links)
            links = cell.find_all('a')
            if links and all('[' in lnk.get_text() for lnk in links):
                continue
            row.append(cell.get_text(strip=True))
        if row:
            rows.append(row)

    # Remove 'Actions' from headers if present
    if 'Actions' in headers:
        headers.remove('Actions')

    return headers, rows, incident_title, info_msg
