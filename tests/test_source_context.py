"""Prepared sources are reused only within an explicit consumer scope."""

from collections.abc import Callable
from pathlib import Path
from typing import override

import pytest
from docutils import nodes
from sphinx.testing.util import SphinxTestApp
from sphinx.util.docutils import SphinxDirective

from sphinx_section_include import read_document, section_source


def _fail_preparation(*, document: nodes.document) -> None:
    """Abort after preparing content which must not escape its scope."""
    document += nodes.paragraph("", "Discard this mutation.")
    message = "Abort this preparation"
    raise ValueError(message)


class ReadContext(SphinxDirective):
    """Expose the parsing context used by extension collectors."""

    @override
    def run(self) -> list[nodes.Node]:
        """Record the active document in source content."""
        return [nodes.paragraph("", "Parsed under " + self.env.docname)]


class ScopedSource(SphinxDirective):
    """Exercise nested source lifetimes using real directive parsing."""

    required_arguments = 1

    @override
    def run(self) -> list[nodes.Node]:
        """Prepare, reuse, and restore sources without retaining a
        cache.
        """
        docname = self.env.docname if self.arguments[0] == "consumer" else None
        with section_source(
            directive=self, source="manual.rst", docname=docname
        ) as first:
            assert (
                "Parsed under " + ("manual" if docname is None else docname)
                in first.astext()
            )
            assert read_document(directive=self, source="manual.rst") is first
            with section_source(directive=self, source="other.rst") as other:
                assert (
                    read_document(directive=self, source="manual.rst") is first
                )
                assert (
                    read_document(directive=self, source="other.rst") is other
                )
                explicit = read_document(
                    directive=self,
                    source="manual.rst",
                    docname=self.env.docname,
                )
                assert (explicit is first) is (docname is not None)
            assert (
                read_document(directive=self, source="other.rst") is not other
            )
            with (
                pytest.raises(expected_exception=ValueError, match="Abort"),
                section_source(directive=self, source="other.rst") as aborted,
            ):
                _fail_preparation(document=aborted)
            assert (
                "Discard this mutation"
                not in read_document(
                    directive=self, source="other.rst"
                ).astext()
            )
            assert read_document(directive=self, source="manual.rst") is first
        assert read_document(directive=self, source="manual.rst") is not first
        return [nodes.paragraph("", "Prepared sources restored.")]


@pytest.mark.parametrize(argnames="consumer_context", argvalues=[False, True])
def test_source_context_restores_nested_sources(
    *,
    make_app: Callable[..., SphinxTestApp],
    tmp_path: Path,
    consumer_context: bool,
) -> None:
    """Prepared trees are bounded by their explicit context lifetime."""
    source = tmp_path / "source"
    source.mkdir()
    _ = (source / "conf.py").write_text(
        data="extensions = ['sphinx_section_include']\n"
    )
    mode = "consumer" if consumer_context else "source"
    _ = (source / "index.rst").write_text(
        data="Index\n=====\n\n.. toctree::\n\n   manual\n   other\n"
        f"\n.. scoped-source:: {mode}\n"
    )
    _ = (source / "manual.rst").write_text(
        data="Manual\n======\n\nSection\n-------\n\nOriginal content.\n"
        "\n.. read-context::\n"
    )
    _ = (source / "other.rst").write_text(
        data="Other\n=====\n\nSection\n-------\n\nOther content.\n"
    )
    app = make_app(srcdir=source, exception_on_warning=True)
    app.add_directive(name="scoped-source", cls=ScopedSource)
    app.add_directive(name="read-context", cls=ReadContext)
    app.build()
    assert (
        "Prepared sources restored."
        in (Path(app.outdir) / "index.html").read_text()
    )
    assert app.warning.getvalue() == ""
