"""Caller-owned transforms run within explicit source-reading scopes."""

from collections import Counter
from collections.abc import Callable
from copy import copy
from functools import partial
from pathlib import Path
from typing import override

import pytest
from docutils import nodes
from docutils.utils import new_document
from sphinx.environment import BuildEnvironment
from sphinx.testing.util import SphinxTestApp
from sphinx.util.docutils import SphinxDirective

from sphinx_section_include import (
    prepare_sources,
    read_document,
    section_source,
)


def write_project(*, root: Path, nested: bool) -> None:
    """Create primary, additional, and unprepared section consumers."""
    root.mkdir()
    files = {
        "conf.py": "extensions = ['sphinx_section_include']\n",
        "index.rst": (
            "Index\n=====\n\n.. toctree::\n\n"
            "   manual\n   other\n   overview\n   outside\n"
        ),
        "manual.rst": (
            "Manual\n======\n\nBefore\n------\n\nPrimary content.\n\n"
            ".. include:: prerequisite.txt\n"
        ),
        "other.rst": (
            "Other\n=====\n\nBefore\n------\n\nSecondary content.\n"
        ),
        "overview.rst": (
            "Overview\n========\n\n.. include-section:: manual.rst\n"
            "   :section: Before\n   :include-heading:\n"
        ),
        "outside.rst": (
            "Outside\n=======\n\n.. include-section:: manual.rst\n"
            "   :section: Before\n   :include-heading:\n"
        ),
        "prerequisite.txt": "Original prerequisite.\n",
    }
    if nested:
        files["index.rst"] += "   nested\n"
        files["manual.rst"] += (
            "\n.. include-section:: nested.rst\n   :section: Shared\n"
        )
        files["nested.rst"] = (
            "Nested\n======\n\nShared\n------\n\nNested prerequisite.\n"
        )
    for name, content in files.items():
        _ = (root / name).write_text(data=content)


def _other_environment(
    *, directive: SphinxDirective, app: SphinxTestApp
) -> SphinxDirective:
    """Use a separate environment with the same files and
    configuration.
    """
    other = copy(x=directive)
    other.state = copy(x=directive.state)
    settings = copy(x=directive.state.document.settings)
    environment = BuildEnvironment(app=app)
    environment.setup(app=app)
    environment.current_document = copy(x=directive.env.current_document)
    settings.env = environment
    other.state.document = new_document(
        source_path=str(
            object=directive.env.doc2path(docname=directive.env.docname)
        ),
        settings=settings,
    )
    return other


def _mark_source(
    document: nodes.document,
    /,
    *,
    marker: list[str],
    observed: list[str],
) -> None:
    """Prepare a tree using values which can change between scopes."""
    observed.append(marker[0])
    document += nodes.paragraph("", marker[0])


def _prepare_inner(document: nodes.document, /) -> None:
    """Replace the surrounding transform without composing with it."""
    document += nodes.paragraph("", "Inner marker.")


def _abort_preparation(document: nodes.document, /) -> None:
    """Fail after mutation to expose accidental retention of that tree."""
    document += nodes.paragraph("", "Aborted mutation.")
    message = "Preparation aborted"
    raise ValueError(message)


@pytest.mark.parametrize(argnames="buildername", argvalues=["html", "text"])
@pytest.mark.parametrize(argnames="consumer_context", argvalues=[False, True])
def test_preparation_covers_composition_sources_and_dependencies(
    *,
    make_app: Callable[..., SphinxTestApp],
    tmp_path: Path,
    buildername: str,
    consumer_context: bool,
) -> None:
    """Preparation precedes selection and respects source reuse and
    scope.
    """
    source = tmp_path / "source"
    write_project(root=source, nested=True)
    _ = (source / "overview.rst").write_text(
        data="Overview\n========\n\n.. prepared-composition::\n\n"
        "   .. include-section:: manual.rst\n      :section: After\n\n"
        "   .. include-section:: manual.rst\n      :section: After\n\n"
        "   .. include-section:: other.rst\n      :section: After\n"
    )
    reads: list[str] = []

    def prepare(document: nodes.document, /) -> None:
        """Rename headings without teaching the library a content
        policy.
        """
        reads.append(next(document.findall(condition=nodes.title)).astext())
        for title in document.findall(condition=nodes.title):
            if title.astext() == "Before":
                title[:] = [nodes.Text(data="After")]

    class PreparedComposition(SphinxDirective):
        """Use standard section includes with a caller-supplied
        transform.
        """

        has_content = True

        @override
        def run(self) -> list[nodes.Node]:
            """Share one prepared source while also transforming other
            reads.
            """
            container = nodes.container()
            with (
                prepare_sources(directive=self, prepare=prepare),
                section_source(
                    directive=self,
                    source="manual.rst",
                    docname=self.env.docname if consumer_context else None,
                ),
            ):
                _ = self.state.nested_parse(
                    block=self.content,
                    input_offset=self.content_offset,
                    node=container,
                )
            return [container]

    app = make_app(
        srcdir=source,
        buildername=buildername,
        exception_on_warning=True,
    )
    app.add_directive(name="prepared-composition", cls=PreparedComposition)
    app.build()
    assert Counter(reads) == Counter({"Nested": 1, "Manual": 1, "Other": 1})
    text = app.env.get_doctree(docname="overview").astext()
    expected_primary = 2
    assert text.count("Primary content.") == expected_primary
    assert "Secondary content." in text
    assert "Original prerequisite." in text
    for docname in ("manual", "outside"):
        original = app.env.get_doctree(docname=docname).astext()
        assert "Before" in original
        assert "After" not in original
    _ = (source / "prerequisite.txt").write_text(
        data="Changed prerequisite.\n"
    )
    app.build()
    assert Counter(reads) == Counter({"Nested": 2, "Manual": 2, "Other": 2})
    updated = app.env.get_doctree(docname="overview").astext()
    assert "Changed prerequisite." in updated
    assert "Original prerequisite." not in updated
    assert app.warning.getvalue() == ""


def test_nested_preparations_restore_trees_and_isolate_environments(
    *, make_app: Callable[..., SphinxTestApp], tmp_path: Path
) -> None:
    """Nested callbacks isolate outer trees and other environments."""
    source = tmp_path / "source"
    write_project(root=source, nested=False)
    _ = (source / "overview.rst").write_text(
        data="Overview\n========\n\n.. inspect-preparation::\n"
    )
    observed: list[str] = []
    marker = ["Outer marker."]

    outer = partial(_mark_source, marker=marker, observed=observed)

    class InspectPreparation(SphinxDirective):
        """Exercise source identity while nesting real preparation
        scopes.
        """

        @override
        def run(self) -> list[nodes.Node]:
            """Restore callbacks and source identity across every exit
            path.
            """
            with section_source(
                directive=self, source="manual.rst"
            ) as original:
                with prepare_sources(directive=self, prepare=outer):
                    with section_source(
                        directive=self, source="manual.rst"
                    ) as prepared:
                        assert prepared is not original
                        assert "Outer marker." in prepared.astext()
                        assert (
                            read_document(directive=self, source="manual.rst")
                            is prepared
                        )
                        other = _other_environment(directive=self, app=app)
                        unprepared = read_document(
                            directive=other, source="manual.rst"
                        )
                        assert "Outer marker." not in unprepared.astext()
                        with (
                            prepare_sources(
                                directive=self, prepare=_prepare_inner
                            ),
                            section_source(
                                directive=self, source="manual.rst"
                            ) as nested,
                        ):
                            assert nested is not prepared
                            assert "Inner marker." in nested.astext()
                            assert "Outer marker." not in nested.astext()
                            assert (
                                read_document(
                                    directive=self, source="manual.rst"
                                )
                                is nested
                            )
                        marker[0] = "Replacement marker."
                        with prepare_sources(directive=self, prepare=outer):
                            replaced = read_document(
                                directive=self, source="manual.rst"
                            )
                            assert replaced is not prepared
                            assert "Replacement marker." in replaced.astext()
                            assert "Outer marker." not in replaced.astext()
                        marker[0] = "Outer marker."
                        with (
                            pytest.raises(
                                expected_exception=ValueError,
                                match="Preparation aborted",
                            ),
                            prepare_sources(
                                directive=self, prepare=_abort_preparation
                            ),
                        ):
                            _ = read_document(
                                directive=self, source="manual.rst"
                            )
                        assert (
                            read_document(directive=self, source="manual.rst")
                            is prepared
                        )
                        assert "Aborted mutation." not in prepared.astext()
                    fresh = read_document(directive=self, source="manual.rst")
                    assert fresh is not prepared
                    assert "Outer marker." in fresh.astext()
                assert (
                    read_document(directive=self, source="manual.rst")
                    is original
                )
                assert "Outer marker." not in original.astext()
            plain = read_document(directive=self, source="manual.rst")
            assert plain is not original
            assert "Outer marker." not in plain.astext()
            assert self.env.docname == "overview"
            return [nodes.paragraph("", "Preparation scopes restored.")]

    app = make_app(srcdir=source, exception_on_warning=True)
    app.add_directive(name="inspect-preparation", cls=InspectPreparation)
    app.build()
    assert observed == [
        "Outer marker.",
        "Replacement marker.",
        "Outer marker.",
    ]
    assert (
        "Preparation scopes restored."
        in app.env.get_doctree(docname="overview").astext()
    )
    assert app.warning.getvalue() == ""
