"""
Schema handler
"""
import yaml
from .config import get_configuration

def load_schema(schema_file=None):
    schema_file = schema_file or get_configuration().schema_loc

    with open(schema_file, 'r') as sf:
        schema = yaml.safe_load(sf)

    if 'tables' not in schema:
        raise ValueError('Tables list missing from schema.')

    if 'types' not in schema:
        raise ValueError('Types missing from schema.')

    return schema
