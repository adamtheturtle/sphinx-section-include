"""Scope caller-owned validation to copied section excerpts."""

from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from docutils import nodes
from sphinx.environment import BuildEnvironment
from sphinx.util.docutils import SphinxDirective


@dataclass(frozen=True, kw_only=True)
class _Validation:
    """One callback active within a Sphinx environment."""

    environment: BuildEnvironment
    validate: Callable[[Sequence[nodes.Node]], None]


_validations: ContextVar[tuple[_Validation, ...]] = ContextVar(
    "section_validations", default=()
)


@contextmanager
def validate_sections(
    *,
    directive: SphinxDirective,
    validate: Callable[[Sequence[nodes.Node]], None],
) -> Generator[None]:
    """Validate copied excerpts within this environment and scope.

    The callback receives each include-section result after exclusions and
    heading conversion, before target registration. It should inspect the
    nodes without mutating them and raise ValueError to reject an excerpt.
    Nested scopes replace their environment's callback and restore it on
    success or failure. Other environments and includes outside the scope are
    unaffected.
    """
    token = _validations.set(
        (
            *_validations.get(),
            _Validation(environment=directive.env, validate=validate),
        )
    )
    try:
        yield
    finally:
        _validations.reset(token)


def validate_content(
    *, directive: SphinxDirective, content: Sequence[nodes.Node]
) -> None:
    """Apply the innermost callback matching this environment."""
    for validation in reversed(_validations.get()):
        if validation.environment is directive.env:
            validation.validate(content)
            return
