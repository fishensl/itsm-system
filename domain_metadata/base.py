"""Canonical field metadata used by API, Vue views and exports.

The registry describes one business field once.  Individual screens select an
ordered profile (list/detail/form/export) instead of redefining labels and
formats independently.
"""
from dataclasses import dataclass, field as dataclass_field
from typing import Mapping


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    data_type: str = 'text'
    group: str = 'basic'
    export_key: str | None = None
    width: int | None = None
    min_width: int | None = None
    default_visible: bool = True
    filterable: bool = False
    sortable: bool = False
    required: bool = False
    sensitive: bool = False
    permission: str | None = None
    value_map: Mapping[str, str] = dataclass_field(default_factory=dict)

    def as_dict(self) -> dict:
        result = {
            'key': self.key,
            'label': self.label,
            'dataType': self.data_type,
            'group': self.group,
            'exportKey': self.export_key or self.key,
            'defaultVisible': self.default_visible,
            'filterable': self.filterable,
            'sortable': self.sortable,
            'required': self.required,
            'sensitive': self.sensitive,
        }
        if self.width is not None:
            result['width'] = self.width
        if self.min_width is not None:
            result['minWidth'] = self.min_width
        if self.permission:
            result['permission'] = self.permission
        if self.value_map:
            result['valueMap'] = dict(self.value_map)
        return result


@dataclass(frozen=True)
class EntitySchema:
    key: str
    label: str
    view_permission: str
    fields: tuple[FieldSpec, ...]
    profiles: Mapping[str, tuple[str, ...]]
    export_presets: Mapping[str, tuple[str, ...]] = dataclass_field(default_factory=dict)
    export_preset_labels: Mapping[str, str] = dataclass_field(default_factory=dict)

    def __post_init__(self):
        field_keys = [item.key for item in self.fields]
        if len(field_keys) != len(set(field_keys)):
            raise ValueError(f'{self.key} contains duplicate field keys')
        known = set(field_keys)
        for profile, keys in self.profiles.items():
            unknown = set(keys) - known
            if unknown:
                raise ValueError(f'{self.key}.{profile} contains unknown fields: {sorted(unknown)}')
        for preset, keys in self.export_presets.items():
            unknown = set(keys) - known
            if unknown:
                raise ValueError(f'{self.key}.{preset} contains unknown preset fields: {sorted(unknown)}')

    @property
    def field_map(self) -> dict[str, FieldSpec]:
        return {item.key: item for item in self.fields}

    def profile_fields(self, profile: str) -> tuple[FieldSpec, ...]:
        keys = self.profiles.get(profile)
        if keys is None:
            raise KeyError(f'unknown profile: {self.key}.{profile}')
        fields = self.field_map
        return tuple(fields[key] for key in keys)

    def export_columns(self, profile: str = 'export_default') -> list[tuple[str, str]]:
        return [(item.export_key or item.key, item.label)
                for item in self.profile_fields(profile)]

    def export_preset_columns(self) -> dict[str, list[str]]:
        fields = self.field_map
        return {
            name: [fields[key].export_key or key for key in keys]
            for name, keys in self.export_presets.items()
        }

    def as_dict(self) -> dict:
        presets = self.export_preset_columns()
        return {
            'key': self.key,
            'label': self.label,
            'profiles': {
                name: [self.field_map[key].as_dict() for key in keys]
                for name, keys in self.profiles.items()
            },
            'exportPresets': [
                {
                    'key': name,
                    'label': self.export_preset_labels.get(name, name),
                    'columns': columns,
                }
                for name, columns in presets.items()
            ],
        }
