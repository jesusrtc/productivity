"""Client-defined JSON attributes, with no prescribed names or content."""
import json
import math


def validate_json(value, depth=0):
    if depth > 8:
        raise ValueError('Attribute values may nest at most 8 levels')
    if value is None or isinstance(value,bool):
        return
    if isinstance(value,(int,float)):
        if isinstance(value,float) and not math.isfinite(value):
            raise ValueError('Attribute numbers must be finite')
        return
    if isinstance(value,str):
        if len(value) > 4096:
            raise ValueError('Attribute text is limited to 4096 characters')
        return
    if isinstance(value,list):
        if len(value) > 100:
            raise ValueError('Attribute lists are limited to 100 values')
        for item in value:
            validate_json(item,depth+1)
        return
    if isinstance(value,dict):
        if len(value) > 100:
            raise ValueError('Use at most 100 attributes per object')
        for name,item in value.items():
            if not isinstance(name,str) or not name.strip() or len(name) > 100:
                raise ValueError('Attribute names must be nonempty text of at most 100 characters')
            validate_json(item,depth+1)
        return
    raise ValueError('Attributes must contain JSON values')


def validate(value):
    if value is not None and not isinstance(value,dict):
        raise ValueError('Attributes must be a JSON object (or null to clear)')
    validate_json(value)
    if len(json.dumps(value,ensure_ascii=False,allow_nan=False).encode()) > 32768:
        raise ValueError('Attributes are limited to 32 KB')


def equal(left, right):
    """Compare JSON types without treating true as 1 or 2.0 as a changed 2."""
    if isinstance(left,dict) and isinstance(right,dict):
        return left.keys() == right.keys() and all(equal(value,right[name]) for name,value in left.items())
    if isinstance(left,list) and isinstance(right,list):
        return len(left) == len(right) and all(equal(a,b) for a,b in zip(left,right))
    if type(left) in (int,float) and type(right) in (int,float):
        return left == right
    return type(left) is type(right) and left == right
