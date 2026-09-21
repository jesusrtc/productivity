"""Each dashboard section is a complete JSON document, separate from notes."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from lab import assistant_records as records, assistant_attributes as attributes, assistant_query as query


RESOURCES = Path(__file__).parent / 'resources' / 'assistant'
CHOICES = dict(source={'active','all','open','documents','starred','completed','cancelled'},
               kind={'','note','meeting','recurring','task'}, match={'any','all'},
               status={'','not_started','in_progress','done','cancelled'},
               sort={'newest','due','priority','title'})


def template():
    return json.loads((RESOURCES/'dashboard-section.json').read_text())


def _validate_legacy(sections):
    if not isinstance(sections,list) or len(sections) > 30:
        raise ValueError('Use at most 30 dashboard sections')
    result, seen = [], set()
    fields = set(LEGACY_SECTION)
    for raw in sections:
        if not isinstance(raw,dict):
            raise ValueError('Each section must be a JSON object')
        if set(raw) - fields:
            raise ValueError('Unknown section fields: ' + ', '.join(sorted(set(raw)-fields)))
        if fields - set(raw):
            raise ValueError('Missing section fields: ' + ', '.join(sorted(fields-set(raw))))
        row = dict(raw)
        identifier = row['id']
        if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',identifier) or identifier in seen:
            raise ValueError('Each dashboard section needs a unique ID (letters, numbers, hyphens, or underscores)')
        seen.add(identifier)
        if type(row['schema']) is not int or row['schema'] != 1:
            raise ValueError('Section schema must be 1')
        if type(row['position']) is not int or not -1000000 <= row['position'] <= 1000000:
            raise ValueError('Section position must be an integer from -1000000 to 1000000')
        for field, maximum in [('title',120),('search',500),('workspace',200),('project',200)]:
            value = row[field]
            if not isinstance(value,str) or len(value) > maximum or field == 'title' and not value.strip():
                raise ValueError('Invalid section ' + field)
        for field, choices in CHOICES.items():
            if not isinstance(row[field],str) or row[field] not in choices:
                raise ValueError('Invalid section ' + field + ': choose ' + ', '.join(repr(value) for value in sorted(choices)))
        if not isinstance(row['priorities'],list) or any(value not in ['P0','P1','P2','P3'] for value in row['priorities']):
            raise ValueError('Section priorities must be an array containing P0, P1, P2, or P3')
        row['priorities'] = list(dict.fromkeys(row['priorities']))
        if row['due_days'] is not None and (type(row['due_days']) is not int or not 0 <= row['due_days'] <= 365):
            raise ValueError('Due window must be 0–365 days or null')
        if type(row['limit']) is not int or row['limit'] not in {0,5,10,20,50,100}:
            raise ValueError('Section limit must be 0 (all), 5, 10, 20, 50, or 100')
        if any(type(row[field]) is not bool for field in ['overdue','starred']):
            raise ValueError('Section toggles must be true or false')
        result.append(row)
    return sorted(result,key=lambda row:(row['position'],row['id']))


# Only used to read the previously shipped flat schema; new defaults live in JSON.
LEGACY_SECTION = dict(schema=1,id='',title='',position=0,source='active',kind='',priorities=[],
                      due_days=None,overdue=True,match='any',status='',starred=False,
                      workspace='',project='',search='',sort='newest',limit=20)


def validate_filter(node, depth=0):
    if depth > 8 or not isinstance(node,dict) or len(node) != 1:
        raise ValueError('Each filter must contain one condition or one and/or group (maximum depth 8)')
    field,value = next(iter(node.items()))
    if field in {'and','or'}:
        if not isinstance(value,list) or not value:
            raise ValueError(field + ' must contain a nonempty array of filters')
        count = 1 + sum(validate_filter(child,depth+1) for child in value)
        if count > 100:
            raise ValueError('Use at most 100 conditions in a section filter')
        return count
    if field in {'source','kind','status'}:
        if not isinstance(value,str) or not value or value not in CHOICES[field]:
            raise ValueError('Invalid filter ' + field + ': choose ' + ', '.join(repr(v) for v in sorted(CHOICES[field]) if v))
    elif field == 'priority':
        if not isinstance(value,list) or not value or any(item not in ['P0','P1','P2','P3'] for item in value):
            raise ValueError('priority must be a nonempty array of P0, P1, P2, or P3')
    elif field == 'due':
        if not isinstance(value,dict) or set(value) != {'within_days','include_overdue'}:
            raise ValueError('due requires within_days and include_overdue')
        if type(value['within_days']) is not int or not 0 <= value['within_days'] <= 365:
            raise ValueError('within_days must be an integer from 0 to 365')
        if type(value['include_overdue']) is not bool:
            raise ValueError('include_overdue must be true or false')
    elif field == 'attribute':
        if not isinstance(value,dict) or 'name' not in value or set(value)-{'name','equals','contains','exists','scope'}:
            raise ValueError('attribute requires name and one of equals, contains, or exists; scope is optional')
        if not isinstance(value['name'],str) or not value['name'].strip() or len(value['name']) > 100:
            raise ValueError('Invalid attribute name')
        operators = set(value) & {'equals','contains','exists'}
        if len(operators) != 1:
            raise ValueError('Use exactly one attribute operator: equals, contains, or exists')
        scope = value.get('scope','document')
        if not isinstance(scope,str) or scope not in {'document','any_tab'}:
            raise ValueError('Attribute scope must be document or any_tab')
        operator = next(iter(operators))
        if operator == 'exists' and type(value[operator]) is not bool:
            raise ValueError('Attribute exists must be true or false')
        attributes.validate_json(value[operator])
    elif field == 'starred':
        if type(value) is not bool:
            raise ValueError('starred must be true or false')
    elif field in {'workspace','project','search'}:
        if not isinstance(value,str) or not value.strip() or len(value) > (500 if field == 'search' else 200):
            raise ValueError('Invalid filter ' + field)
    else:
        raise ValueError('Unknown filter condition: ' + field)
    return 1


def validate(sections):
    if not isinstance(sections,list) or len(sections) > 30:
        raise ValueError('Use at most 30 dashboard sections')
    result,seen = [],set()
    common = {'schema','id','title','position','sort','limit'}
    for row in sections:
        if not isinstance(row,dict):
            raise ValueError('Each section must be a JSON object')
        fields = common | ({'where'} if row.get('schema') == 3 else {'filter'})
        if set(row) != fields:
            missing,unknown = fields-set(row),set(row)-fields
            raise ValueError('Invalid section fields. ' + ('Missing: '+', '.join(sorted(missing))+'. ' if missing else '')
                             + ('Unknown: '+', '.join(sorted(unknown))+'.' if unknown else ''))
        identifier = row['id']
        if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',identifier) or identifier in seen:
            raise ValueError('Each section needs a unique ID (letters, numbers, hyphens, or underscores)')
        seen.add(identifier)
        if type(row['schema']) is not int or row['schema'] not in {2,3}:
            raise ValueError('Section schema must be 2 or 3')
        if not isinstance(row['title'],str) or not row['title'].strip() or len(row['title']) > 120:
            raise ValueError('Invalid section title')
        if type(row['position']) is not int or not -1000000 <= row['position'] <= 1000000:
            raise ValueError('Section position must be an integer from -1000000 to 1000000')
        if not isinstance(row['sort'],str) or row['sort'] not in CHOICES['sort']:
            raise ValueError('sort must be newest, due, priority, or title')
        if type(row['limit']) is not int or row['limit'] not in {0,5,10,20,50,100}:
            raise ValueError('limit must be 0 (all), 5, 10, 20, 50, or 100')
        if row['schema'] == 3:
            if not isinstance(row['where'],str):
                raise ValueError('where must be SQL-style filter text')
            query.parse(row['where'])
        else:
            validate_filter(row['filter'])
        result.append(row)
    return sorted(result,key=lambda row:(row['position'],row['id']))


def upgrade(row):
    if row.get('schema') == 2:
        validate([row])
        where = query.from_filter(row['filter'])
        if next(iter(row['filter'])) in {'and','or'}:
            where = where[1:-1]
        return dict(schema=3,id=row['id'],title=row['title'],position=row['position'],where=where,sort=row['sort'],limit=row['limit'])
    if row.get('schema') != 1:
        return row
    old = _validate_legacy([row])[0]
    clauses = [{'starred':True} if old['source']=='starred' else {'source':old['source']}]
    planning = []
    if old['priorities']:
        planning.append({'priority':old['priorities']})
    if old['due_days'] is not None:
        planning.append({'due':{'within_days':old['due_days'],'include_overdue':old['overdue']}})
    if planning:
        clauses.append(planning[0] if len(planning)==1 else {'or' if old['match']=='any' else 'and':planning})
    for field in ['kind','status','workspace','project','search']:
        if old[field]:
            clauses.append({field:old[field]})
    if old['starred'] and old['source']!='starred':
        clauses.append({'starred':True})
    return upgrade(dict(schema=2,id=old['id'],title=old['title'],position=old['position'],
                filter=clauses[0] if len(clauses)==1 else {'and':clauses},sort=old['sort'],limit=old['limit']))


def _read(root):
    directory = records.safe(root,root/'.assistant/dashboard')
    legacy = records.safe(root,root/'.assistant/dashboard.json')
    if directory.exists():
        sections = []
        for source in sorted(directory.glob('*.json')):
            row = json.loads(records.safe(root,source).read_text())
            if not isinstance(row,dict) or row.get('id') != source.stem:
                raise ValueError('Section ID must match its filename: ' + source.name)
            sections.append(upgrade(row))
    elif legacy.exists():
        value = json.loads(legacy.read_text())
        if not isinstance(value,dict) or value.get('schema') != 1 or not isinstance(value.get('sections'),list):
            raise ValueError('Unsupported dashboard settings')
        sections = []
        for index,row in enumerate(value['sections']):
            if not isinstance(row,dict):
                raise ValueError('Each section must be a JSON object')
            sections.append(upgrade({**LEGACY_SECTION, **row, 'schema':1, 'position':index*10}))
    else:
        sections = [json.loads(path.read_text()) for path in sorted((RESOURCES/'dashboard').glob('*.json'))]
    sections = validate(sections)
    revision = hashlib.sha256(json.dumps(sections,sort_keys=True).encode()).hexdigest()
    return dict(sections=sections,revision=revision,section_template=template(),
                compiled_filters={row['id']:query.parse(row['where']) for row in sections})


def read(root):
    # Share the writer lock so a list never observes a partial batch update.
    with records.lock(root):
        return _read(root)


def _write(root, sections):
    directory = records.safe(root,root/'.assistant/dashboard')
    if not directory.exists():
        # Initialize/migrate the complete directory in one rename. Retain legacy JSON.
        staging = Path(tempfile.mkdtemp(prefix='.dashboard-',dir=root/'.assistant'))
        try:
            for row in sections:
                records.write_json(staging/(row['id']+'.json'),row)
            staging.rename(directory)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return
    existing = {records.safe(root,path):path.read_bytes() for path in directory.glob('*.json')}
    old_schema = min((json.loads(content).get('schema',3) for content in existing.values()),default=3)
    if old_schema < 3:
        digest = hashlib.sha256(b''.join(path.name.encode()+b'\0'+content for path,content in sorted(existing.items()))).hexdigest()[:16]
        backup = records.safe(root,root/'.assistant/backups'/('dashboard-schema-'+str(old_schema)+'-'+digest))
        backup.mkdir(parents=True,exist_ok=True)
        for path,content in existing.items():
            target = records.safe(root,backup/path.name)
            if not target.exists():
                records.atomic_bytes(target,content)
            elif target.read_bytes() != content:
                raise ValueError('Dashboard backup already exists with different content')
    desired = {records.safe(root,directory/(row['id']+'.json')):row for row in sections}
    try:
        for path,row in desired.items():
            if path not in existing or json.loads(existing[path]) != row:
                records.write_json(path,row)
        for path in existing.keys() - desired.keys():
            path.unlink()
    except OSError:
        for path,content in existing.items():
            records.atomic_bytes(path,content)
        for path in desired.keys() - existing.keys():
            path.unlink(missing_ok=True)
        raise


def write(root, sections, *, expected):
    sections = validate([upgrade(row) for row in validate(sections)])
    with records.lock(root):
        if _read(root)['revision'] != expected:
            raise ValueError('Dashboard changed elsewhere. Reopen Show filter to load the latest JSON.')
        _write(root,sections)
        return _read(root)


def migrate(root):
    """Materialize existing settings without changing section behavior or order."""
    with records.lock(root):
        current = _read(root)
        _write(root,current['sections'])
        return _read(root)
