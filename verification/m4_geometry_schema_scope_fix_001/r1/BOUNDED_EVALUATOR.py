def accepts(schema, value):
    if isinstance(schema, bool):
        return schema
    supported = {'type', 'properties', 'required', 'additionalProperties', 'oneOf', 'anyOf', 'allOf', 'if', 'then', 'enum', 'const', 'minItems', 'maxItems', 'uniqueItems', 'items', 'contains', 'minLength', 'maxLength', 'description', 'default'}
    unknown = set(schema) - supported
    if unknown:
        raise AssertionError('unsupported visited schema keyword ' + str(unknown))
    VISITED.update(schema)
    kind = schema.get('type')
    if kind is not None:
        tests = {'object': type(value) is dict, 'array': type(value) is list, 'string': type(value) is str, 'boolean': type(value) is bool, 'number': type(value) in (int, float), 'integer': type(value) is int}
        if kind not in tests:
            raise AssertionError('unknown type')
        if not tests[kind]:
            return False
    if 'enum' in schema and value not in schema['enum']:
        return False
    if 'const' in schema and value != schema['const']:
        return False
    if isinstance(value, dict):
        if any((key not in value for key in schema.get('required', ()))):
            return False
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False and set(value) - set(properties):
            return False
        if any((not accepts(properties[key], item) for key, item in value.items() if key in properties)):
            return False
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', float('inf')):
            return False
        if schema.get('uniqueItems') and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            return False
        if 'items' in schema and any((not accepts(schema['items'], item) for item in value)):
            return False
        if 'contains' in schema and (not any((accepts(schema['contains'], item) for item in value))):
            return False
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', float('inf')):
            return False
    if 'allOf' in schema and (not all((accepts(item, value) for item in schema['allOf']))):
        return False
    if 'anyOf' in schema and (not any((accepts(item, value) for item in schema['anyOf']))):
        return False
    if 'oneOf' in schema and sum((accepts(item, value) for item in schema['oneOf'])) != 1:
        return False
    if 'if' in schema and accepts(schema['if'], value) and ('then' in schema) and (not accepts(schema['then'], value)):
        return False
    return True
