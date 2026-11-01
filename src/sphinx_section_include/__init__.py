"""Include parsed reStructuredText sections in Sphinx documentation."""

from importlib.metadata import version

from sphinx.application import Sphinx

from sphinx_section_include.directive import (
    IncludeSection,
    resolve_included_references,
)
from sphinx_section_include.reader import (
    read_document,
    resolve_source,
    section_source,
)
from sphinx_section_include.sections import (
    copy_section,
    find_sections,
    select_section,
)

__all__ = [
    "copy_section",
    "find_sections",
    "read_document",
    "resolve_source",
    "section_source",
    "select_section",
]
__version__ = version(distribution_name="sphinx-section-include")


def setup(app: Sphinx) -> dict[str, object]:
    """Register the directive and builder-independent reference
    handling.
    """
    app.add_directive(name="include-section", cls=IncludeSection)
    _ = app.connect(
        event="doctree-resolved", callback=resolve_included_references
    )
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
