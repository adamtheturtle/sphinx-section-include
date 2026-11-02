"""Include parsed reStructuredText sections in Sphinx documentation."""

from importlib.metadata import version

from sphinx.application import Sphinx
from sphinx.util.typing import ExtensionMetadata

from sphinx_section_include.directive import (
    IncludeSection,
    resolve_included_references,
)
from sphinx_section_include.reader import (
    prepare_sources,
    read_document,
    resolve_source,
    section_source,
)
from sphinx_section_include.sections import (
    copy_section,
    find_sections,
    select_section,
)
from sphinx_section_include.validation import validate_sections

__all__ = [
    "copy_section",
    "find_sections",
    "prepare_sources",
    "read_document",
    "resolve_source",
    "section_source",
    "select_section",
    "validate_sections",
]
__version__ = version(distribution_name="sphinx-section-include")


def setup(app: Sphinx) -> ExtensionMetadata:
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
