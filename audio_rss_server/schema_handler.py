"""
Schema handler
"""
import os
from ruamel import yaml
from .config import get_configuration

def load_schema(schema_file=None):
    schema_file = schema_file or get_configuration().schema_loc
    schema_file = os.path.abspath(schema_file)

    schema_cache = getattr(load_schema, '_schemas', {})
    if schema_file in schema_cache:
        return schema_cache[schema_file]

    with open(schema_file, 'r') as sf:
        schema = yaml.safe_load(sf)

    if 'tables' not in schema:
        raise ValueError('Tables list missing from schema.')

    if 'types' not in schema:
        raise ValueError('Types missing from schema.')

    schema_cache[schema_file] = schema

    return schema_cache[schema_file]
