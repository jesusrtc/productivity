"""Parse the dashboard's small SQL-style WHERE language; never execute SQL/code."""
import json
import math
import re
from functools import lru_cache

from lab import assistant_attributes as attributes

TOKEN = re.compile(r"\s+|(?P<string>'(?:[^']|'')*')|(?P<quoted>\"(?:[^\"]|\"\")*\")|(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)|(?P<word>[A-Za-z_][A-Za-z_0-9]*)|(?P<op><=|>=|!=|<>|[=<>(),.+-])")
BUILTINS = {'source','kind','status','priority','due','starred','workspace','project','search',
            'title','summary','tldr','owner','date','created','updated','tracked','keep_in_documents','note_type','type'}
CATEGORIES = {'source':{'active','all','open','documents','starred','completed','cancelled'},
              'kind':{'note','meeting','recurring','task'}}


class Parser:
    def __init__(self, text):
        if not isinstance(text,str) or not text.strip() or len(text) > 32768:
            raise ValueError('where must be nonempty text of at most 32768 characters')
        self.tokens = []
        position = 0
        while position < len(text):
            match = TOKEN.match(text,position)
            if not match:
                raise ValueError(f'Invalid filter character at position {position+1}')
            if match.lastgroup:
                self.tokens.append((match.lastgroup,match.group(),position))
            position = match.end()
        if len(self.tokens) > 1200:
            raise ValueError('Filter is too long; use at most 100 conditions')
        self.tokens.append(('end','',len(text)))
        self.index = self.conditions = 0

    def error(self, message):
        raise ValueError(f'{message} at position {self.tokens[self.index][2]+1}')

    def accept(self, value):
        kind,text,_ = self.tokens[self.index]
        if kind in {'word','op'} and text.upper() == value:
            self.index += 1
            return True
        return False

    def require(self, value):
        if not self.accept(value): self.error('Expected '+value)

    def expression(self, depth=0):
        if depth > 16: self.error('Filter nesting is limited to 16 levels')
        children = [self.conjunction(depth)]
        while self.accept('OR'): children.append(self.conjunction(depth))
        return children[0] if len(children)==1 else {'or':children}

    def conjunction(self, depth):
        children = [self.term(depth)]
        while self.accept('AND'): children.append(self.term(depth))
        return children[0] if len(children)==1 else {'and':children}

    def term(self, depth):
        if depth > 16: self.error('Filter nesting is limited to 16 levels')
        if self.accept('NOT'): return {'not':self.term(depth+1)}
        if self.accept('('):
            node = self.expression(depth+1)
            self.require(')')
            return node
        if self.accept('TRUE'): return {'constant':True}
        if self.accept('FALSE'): return {'constant':False}
        return self.predicate()

    def identifier(self):
        kind,text,_ = self.tokens[self.index]
        if kind not in {'word','quoted'}: self.error('Expected a field name')
        self.index += 1
        return text[1:-1].replace('""','"') if kind=='quoted' else text

    def field(self):
        name = self.identifier()
        if self.accept('.'):
            if name.lower() not in {'attributes','any_tab'}:
                self.error('Use attributes.name or any_tab.name')
            scope = 'any_tab' if name.lower()=='any_tab' else 'document'
            name = self.identifier()
        else:
            scope = 'builtin' if name.lower() in BUILTINS else 'document'
            if scope == 'builtin': name = name.lower()
        if not name.strip() or len(name)>100: self.error('Invalid field name')
        return {'name':name,'scope':scope}

    def value(self):
        if self.accept('TODAY') or self.accept('CURRENT_DATE'):
            if self.accept('('): self.require(')')
            sign = 1 if self.accept('+') else -1 if self.accept('-') else 0
            days = 0
            if sign:
                kind,text,_ = self.tokens[self.index]
                if kind!='number' or not text.isdigit() or int(text)>36500:
                    self.error('Expected an integer day offset between 0 and 36500')
                self.index += 1
                days = sign*int(text)
            return {'today':days}
        if self.accept('TRUE'): return {'literal':True}
        if self.accept('FALSE'): return {'literal':False}
        if self.accept('NULL'): return {'literal':None}
        if self.accept('JSON'):
            kind,text,_ = self.tokens[self.index]
            if kind!='string': self.error('Expected a single-quoted JSON value')
            self.index += 1
            try: value = json.loads(text[1:-1].replace("''", "'"))
            except ValueError: self.error('Invalid JSON value')
            attributes.validate_json(value)
            return {'json':value}
        sign = -1 if self.accept('-') else 1
        kind,text,_ = self.tokens[self.index]
        if kind=='number':
            self.index += 1
            value = sign*(float(text) if any(c in text for c in '.eE') else int(text))
            if isinstance(value,float) and not math.isfinite(value): self.error('Expected a finite number')
            return {'literal':value}
        if sign==1 and kind=='string':
            self.index += 1
            value = text[1:-1].replace("''", "'")
            attributes.validate_json(value)
            return {'literal':value}
        self.error('Expected a quoted string, number, TRUE, FALSE, NULL, or TODAY')

    def predicate(self):
        self.conditions += 1
        if self.conditions > 100: self.error('Use at most 100 conditions')
        field = self.field()
        op = None
        node = {'field':field}
        if self.accept('IS'):
            negate = self.accept('NOT')
            op = 'is_null' if self.accept('NULL') else 'is_missing' if self.accept('MISSING') else None
            if op is None: self.error('Expected NULL or MISSING')
            if negate: op = op.replace('is_','is_not_')
        else:
            negate = self.accept('NOT')
            for sql,operator in [('IN','in'),('BETWEEN','between'),('LIKE','like'),('CONTAINS','contains'),
                                  ('=','eq'),('!=','ne'),('<>','ne'),('<=','le'),('>=','ge'),('<','lt'),('>','gt')]:
                if self.accept(sql):
                    op = operator
                    break
            if negate and op not in {'in','between','like','contains'}:
                self.error('Expected IN, BETWEEN, LIKE, or CONTAINS after NOT')
            if op == 'in':
                self.require('(')
                values = [self.value()]
                while self.accept(','): values.append(self.value())
                self.require(')')
                if len(values)>100: self.error('IN allows at most 100 values')
                node['values'] = values
            elif op:
                node['value'] = self.value()
                if op == 'between':
                    self.require('AND')
                    node['upper'] = self.value()
                if op == 'like' and not isinstance(node['value'].get('literal'),str):
                    self.error('LIKE needs a quoted text pattern')
            else:
                op = 'eq'
                node['value'] = {'literal':True}
            if negate: node['negate'] = True
        node['op'] = op
        if field['scope']=='builtin' and field['name'] in CATEGORIES:
            category = field['name']
            if op not in {'eq','ne','in'}: self.error(category+' supports =, !=, or IN')
            values = node.get('values',[node.get('value')])
            if any(not v or not isinstance(v.get('literal'),str) or v['literal'] not in CATEGORIES[category] for v in values):
                self.error('Invalid '+category+'; choose '+', '.join(sorted(CATEGORIES[category])))
            leaves = [{category:v['literal']} for v in values]
            result = leaves[0] if len(leaves)==1 else {'or':leaves}
            return {'not':result} if op=='ne' or node.get('negate') else result
        if field=={'name':'search','scope':'builtin'}:
            if op!='contains' or not isinstance(node.get('value',{}).get('literal'),str):
                self.error('search supports CONTAINS with quoted text')
            result = {'search':node['value']['literal']}
            return {'not':result} if node.get('negate') else result
        return {'compare':node}


@lru_cache(maxsize=128)
def parse(text):
    parser = Parser(text)
    parser.accept('WHERE')
    result = parser.expression()
    if parser.tokens[parser.index][0]!='end': parser.error('Unexpected token')
    return result


def literal(value):
    if value is None: return 'NULL'
    if value is True: return 'true'
    if value is False: return 'false'
    if isinstance(value,str): return "'"+value.replace("'","''")+"'"
    if isinstance(value,(int,float)): return json.dumps(value,allow_nan=False)
    return 'JSON '+literal(json.dumps(value,ensure_ascii=False,separators=(',',':')))


def field_name(name):
    return name if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name) else '"'+name.replace('"','""')+'"'


def from_filter(node):
    """Preserve schema-2 grouping and exact attribute semantics in SQL text."""
    field,value = next(iter(node.items()))
    if field in {'and','or'}:
        return '('+(' '+field.upper()+' ').join(from_filter(child) for child in value)+')'
    if field=='priority': return 'priority IN ('+', '.join(literal(item) for item in value)+')'
    if field=='due':
        end = 'TODAY + '+str(value['within_days'])
        return 'due <= '+end if value['include_overdue'] else 'due BETWEEN TODAY AND '+end
    if field=='search': return 'search CONTAINS '+literal(value)
    if field=='attribute':
        name = ('any_tab.' if value.get('scope')=='any_tab' else 'attributes.')+field_name(value['name'])
        if 'exists' in value: return name+(' IS NOT MISSING' if value['exists'] else ' IS MISSING')
        # JSON null is an exact literal here, unlike SQL's unknown NULL comparison.
        if 'equals' in value: return name+' = '+('JSON \'null\'' if value['equals'] is None else literal(value['equals']))
        return name+' CONTAINS '+('JSON \'null\'' if value['contains'] is None else literal(value['contains']))
    return field+' = '+literal(value)
