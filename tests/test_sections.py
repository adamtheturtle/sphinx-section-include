"""Selection and copying preserve parsed document semantics."""

import pytest
from docutils import nodes
from docutils.core import publish_doctree

from sphinx_section_include import copy_section, find_sections, select_section

SOURCE = """\
Manual
======

First
-----

.. _stable-brief:

Brief
~~~~~

First instructions.

Details
^^^^^^^

Nested details.

Brief / Details
~~~~~~~~~~~~~~~

A literal slash heading.

Second
------

Brief
~~~~~

Second instructions.
"""


@pytest.mark.parametrize(
    argnames=("selector", "expected"),
    argvalues=[
        ("First", "First"),
        ("First / Brief", "Brief"),
        ("#stable-brief", "Brief"),
        ("First / Brief / Details", "Details"),
        ("Brief / Details", "Brief / Details"),
    ],
)
def test_selectors(*, selector: str, expected: str) -> None:
    """Names, paths, and labels identify the intended source section."""
    doc = publish_doctree(source=SOURCE)
    assert (
        select_section(document=doc, selector=selector)[0].astext() == expected
    )


@pytest.mark.parametrize(
    argnames="selector",
    argvalues=["Missing", "Brief", "#missing", "First / Missing", ""],
)
def test_missing_or_ambiguous(*, selector: str) -> None:
    """Callers can inspect matches or require exactly one selection."""
    doc = publish_doctree(source=SOURCE)
    assert len(find_sections(document=doc, selector=selector)) != 1
    with pytest.raises(
        expected_exception=ValueError, match="Expected one section"
    ):
        _ = select_section(document=doc, selector=selector)


@pytest.mark.parametrize(argnames="include_heading", argvalues=[False, True])
def test_copy_is_independent(*, include_heading: bool) -> None:
    """Copying keeps node structure, anchors, and metadata without
    mutation.
    """
    doc = publish_doctree(source=SOURCE, source_path="original.rst")
    part = select_section(document=doc, selector="First")
    brief = select_section(document=part, selector="#stable-brief")
    details = select_section(document=brief, selector="Details")
    original = part.pformat()
    content = copy_section(
        section=part,
        include_heading=include_heading,
        exclude_sections=(details, details),
    )
    container = nodes.container()
    container.extend(item=content)
    assert "Nested details." not in container.astext()
    assert "A literal slash heading." in container.astext()
    assert part.pformat() == original
    assert all(
        node.source == "original.rst"
        for node in container.findall(condition=nodes.section)
    )
    if include_heading:
        assert isinstance(content[0], nodes.section)
        assert content[0]["ids"] == part["ids"]
    else:
        assert (
            next(container.findall(condition=nodes.section))[0].astext()
            == "Brief"
        )
    assert not any(
        node is brief for node in container.findall(condition=nodes.section)
    )


@pytest.mark.parametrize(argnames="selector", argvalues=["First", "Second"])
def test_exclusions_require_descendants(*, selector: str) -> None:
    """An exclusion cannot silently target the root or an unrelated
    section.
    """
    doc = publish_doctree(source=SOURCE)
    part = select_section(document=doc, selector="First")
    excluded = select_section(document=doc, selector=selector)
    with pytest.raises(
        expected_exception=ValueError, match="must be descendants"
    ):
        _ = copy_section(
            section=part, include_heading=True, exclude_sections=(excluded,)
        )
