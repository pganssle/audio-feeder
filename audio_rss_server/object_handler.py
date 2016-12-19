"""
Book handlers
"""

from .schema_handler import load_schema

class BaseObject(object):
    PROPERTIES = tuple()
    
    def __init__(self, **kwargs):
        base_kwargs = {k: None for k in self.PROPERTIES}

        extra_kwargs = set(kwargs.keys()) - set(base_kwargs)

        if len(extra_kwargs):
            raise TypeError('__init__ got unexpected keywords:' + 
                            ','.join("'{}'".format(k) for k in extra_kwargs) +
                            '.')

        base_kwargs.update(kwargs)

        for k, v in base_kwargs.items():
            setattr(self, k, v)

    def to_dict(self):
        return {k: getattr(self, k) for k in self.PROPERTIES}


def object_factory(name, properties, bases=(BaseObject, )):
    PROPERTIES = tuple(properties)
    return type(name, bases, {'PROPERTIES': PROPERTIES})


def load_classes(schema=None):
    args = (schema,) if schema else tuple()
    schema = load_schema(*args)

    type_dict = {}

    for ctype_name, ctype_props in schema['types'].items():
        ctype = object_factory(ctype_name, BaseObject, ctype_props)

        type_dict[ctype_name] = ctype

    globals().update(type_dict)

# Use the base schema to generate the classes.
load_classes()

