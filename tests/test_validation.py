"""Validate copied excerpts without replacing the standard directive."""

from collections.abc import Callable, Sequence
from copy import copy
from pathlib import Path
from typing import override

import pytest
from docutils import nodes
from docutils.utils import new_document
from sphinx.environment import BuildEnvironment
from sphinx.testing.util import SphinxTestApp
from sphinx.util.docutils import SphinxDirective

from sphinx_section_include import section_source, validate_sections


def _write_project(*, root: Path, composition: str) -> None:
    """Create a source with included and excluded descendant content."""
    root.mkdir()
    files = {
        "conf.py": "extensions = ['sphinx_section_include']\n",
        "index.rst": (
            "Index\n=====\n\n.. toctree::\n\n   manual\n   overview\n"
        ),
        "manual.rst": (
            "Manual\n======\n\nEntry\n-----\n\nPublic content.\n\n"
            "Secret\n~~~~~~\n\nExcluded content.\n"
        ),
        "overview.rst": "Overview\n========\n\n" + composition,
    }
    for name, content in files.items():
        _ = (root / name).write_text(data=content)


def _include(*, directive: SphinxDirective) -> nodes.container:
    """Parse ordinary section includes in the directive's current
    scope.
    """
    container = nodes.container()
    _ = directive.state.nested_parse(
        block=directive.content,
        input_offset=directive.content_offset,
        node=container,
    )
    return container


def _other_environment(
    *, directive: SphinxDirective, app: SphinxTestApp
) -> SphinxDirective:
    """Parse with a distinct environment sharing the same source files."""
    other = copy(x=directive)
    other.state = copy(x=directive.state)
    settings = copy(x=directive.state.document.settings)
    environment = BuildEnvironment(app=app)
    environment.setup(app=app)
    environment.current_document = copy(x=directive.env.current_document)
    settings.env = environment
    other.state.document = new_document(
        source_path=str(object=directive.env.doc2path(docname="overview")),
        settings=settings,
    )
    other.state.memo = copy(x=directive.state.memo)
    other.state.memo.document = other.state.document
    return other


@pytest.mark.parametrize(argnames="buildername", argvalues=["html", "text"])
def test_validation_sees_each_copied_selection(
    *,
    make_app: Callable[..., SphinxTestApp],
    tmp_path: Path,
    buildername: str,
) -> None:
    """Validate after exclusions and heading conversion, including
    reuse.
    """
    source = tmp_path / "source"
    excerpt = (
        "   .. include-section:: manual.rst\n      :section: Entry\n"
        "      :include-heading:\n      :heading-style: rubric\n"
        "      :exclude-sections: Secret\n\n"
    )
    _write_project(
        root=source,
        composition=".. validated-composition::\n\n"
        + excerpt * 2
        + ".. include-section:: manual.rst\n   :section: Entry\n",
    )
    copies: list[nodes.rubric] = []

    def validate(content: Sequence[nodes.Node], /) -> None:
        """Inspect the actual excerpt rather than its unfiltered
        source.
        """
        assert isinstance(content[0], nodes.rubric)
        assert content[0].astext() == "Entry"
        text = "\n".join(node.astext() for node in content)
        assert "Public content." in text
        assert "Excluded content." not in text
        assert content[0]["ids"] == ["entry"]
        copies.append(content[0])

    class ValidatedComposition(SphinxDirective):
        """Share one source while validating every copied excerpt."""

        has_content = True

        @override
        def run(self) -> list[nodes.Node]:
            """Use the standard directive without overriding
            registration.
            """
            with (
                section_source(directive=self, source="manual.rst"),
                validate_sections(directive=self, validate=validate),
            ):
                return [_include(directive=self)]

    app = make_app(
        srcdir=source, buildername=buildername, exception_on_warning=True
    )
    app.add_directive(name="validated-composition", cls=ValidatedComposition)
    app.build()
    expected_copies = 2
    assert len(copies) == expected_copies
    assert copies[0] is not copies[1]
    assert copies[0]["ids"] != copies[1]["ids"]
    assert (
        "Excluded content." in app.env.get_doctree(docname="manual").astext()
    )
    assert (
        "Excluded content." in app.env.get_doctree(docname="overview").astext()
    )
    assert app.warning.getvalue() == ""


def test_nested_validators_restore_after_success_and_failure(
    *, make_app: Callable[..., SphinxTestApp], tmp_path: Path
) -> None:
    """Nested callbacks replace outer validation and isolate
    environments.
    """
    source = tmp_path / "source"
    _write_project(
        root=source,
        composition=".. inspect-validation::\n\n"
        "   .. include-section:: manual.rst\n      :section: Entry\n",
    )
    observed: list[str] = []

    def outer(content: Sequence[nodes.Node], /) -> None:
        """Record the outer callback once per copied selection."""
        assert bool(content)
        observed.append("outer")

    def inner(content: Sequence[nodes.Node], /) -> None:
        """Replace the outer callback within this environment."""
        assert bool(content)
        observed.append("inner")

    def reject(content: Sequence[nodes.Node], /) -> None:
        """Expose cleanup when a callback aborts parsing."""
        assert bool(content)
        message = "Validation aborted"
        raise RuntimeError(message)

    class InspectValidation(SphinxDirective):
        """Nest scopes around ordinary include directives."""

        has_content = True

        @override
        def run(self) -> list[nodes.Node]:
            """Restore callbacks after both exits and leave no active
            scope.
            """
            with validate_sections(directive=self, validate=outer):
                _ = _include(directive=self)
                with validate_sections(directive=self, validate=inner):
                    _ = _include(directive=self)
                _ = _include(directive=self)
                with (
                    pytest.raises(
                        expected_exception=RuntimeError,
                        match="Validation aborted",
                    ),
                    validate_sections(directive=self, validate=reject),
                ):
                    _ = _include(directive=self)
                _ = _include(directive=self)
                other = _other_environment(directive=self, app=app)
                _ = _include(directive=other)
                with validate_sections(directive=other, validate=inner):
                    _ = _include(directive=self)
                    _ = _include(directive=other)
            return [_include(directive=self)]

    app = make_app(
        srcdir=source, buildername="text", exception_on_warning=True
    )
    app.add_directive(name="inspect-validation", cls=InspectValidation)
    app.build()
    assert observed == ["outer", "inner", "outer", "outer", "outer", "inner"]
    assert app.warning.getvalue() == ""


def test_validation_failure_has_directive_location(
    *, make_app: Callable[..., SphinxTestApp], tmp_path: Path
) -> None:
    """Report a caller's ValueError as an ordinary include diagnostic."""
    source = tmp_path / "source"
    _write_project(
        root=source,
        composition=".. validated-composition::\n\n"
        "   .. include-section:: manual.rst\n      :section: Entry\n",
    )

    def reject(content: Sequence[nodes.Node], /) -> None:
        """Keep the rejection rule entirely within the consumer."""
        assert bool(content)
        message = "Consumer rejected this excerpt"
        raise ValueError(message)

    class ValidatedComposition(SphinxDirective):
        """Report validation errors through the standard include directive."""

        has_content = True

        @override
        def run(self) -> list[nodes.Node]:
            """Keep the callback active only while this content is
            parsed.
            """
            with validate_sections(directive=self, validate=reject):
                return [_include(directive=self)]

    app = make_app(srcdir=source, buildername="text")
    app.add_directive(name="validated-composition", cls=ValidatedComposition)
    app.build()
    warning = app.warning.getvalue()
    assert "overview.rst:6: ERROR: Consumer rejected this excerpt" in warning
