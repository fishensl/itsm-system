"""Public access to canonical entity metadata."""
from domain_metadata.entities import ENTITY_SCHEMAS


def get_entity_schema(entity: str):
    return ENTITY_SCHEMAS.get(entity)


def entity_metadata(entities=None):
    names = entities or ENTITY_SCHEMAS.keys()
    return {name: ENTITY_SCHEMAS[name].as_dict() for name in names if name in ENTITY_SCHEMAS}


__all__ = ['ENTITY_SCHEMAS', 'entity_metadata', 'get_entity_schema']
