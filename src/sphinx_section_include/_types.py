"""Narrow values read from Docutils' dynamically typed attributes."""

from typing import TypeGuard


def is_list(value: object, /) -> TypeGuard[list[object]]:
    """Identify a list with no assumptions about its elements."""
    return isinstance(value, list)


def _is_tuple(value: object, /) -> TypeGuard[tuple[object, ...]]:
    """Identify a tuple with no assumptions about its elements."""
    return isinstance(value, tuple)


def is_string_list(value: object, /) -> TypeGuard[list[str]]:
    """Identify a Docutils ID or name list."""
    return is_list(value) and all(isinstance(item, str) for item in value)


def is_string_tuple(value: object, /) -> TypeGuard[tuple[str, ...]]:
    """Identify a path written by the section include extension."""
    return _is_tuple(value) and all(isinstance(item, str) for item in value)


def is_heading_paths(
    value: object, /
) -> TypeGuard[tuple[tuple[str, ...], ...]]:
    """Identify the parsed list of excluded heading paths."""
    return _is_tuple(value) and all(is_string_tuple(item) for item in value)
