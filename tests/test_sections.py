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

.. _deep-label:

Deep / nested
^^^^^^^^^^^^^

Literal path component.

#stable-brief
~~~~~~~~~~~~~

A literal hash heading.

Second
------

Brief
~~~~~

Second instructions.
"""


@pytest.mark.parametrize(
    argnames=("title", "path", "label", "expected"),
    argvalues=[
        ("First", None, None, "First"),
        (None, ("First", "Brief"), None, "Brief"),
        (None, None, "stable-brief", "Brief"),
        (None, ("First", "Brief", "Details"), None, "Details"),
        (None, ("Brief", "Details"), None, "Details"),
        ("Brief / Details", None, None, "Brief / Details"),
        (
            None,
            ("First", "Brief / Details", "Deep / nested"),
            None,
            "Deep / nested",
        ),
        ("#stable-brief", None, None, "#stable-brief"),
        (None, None, "deep-label", "Deep / nested"),
    ],
)
def test_explicit_selectors(
    *,
    title: str | None,
    path: tuple[str, ...] | None,
    label: str | None,
    expected: str,
) -> None:
    """Literal titles, component paths, and labels cannot shadow one
    another.
    """
    doc = publish_doctree(source=SOURCE)
    assert (
        select_section(document=doc, title=title, path=path, label=label)[
            0
        ].astext()
        == expected
    )


@pytest.mark.parametrize(
    argnames=("title", "path", "label"),
    argvalues=[
        ("Missing", None, None),
        ("Brief", None, None),
        ("First / Brief", None, None),
        ("#deep-label", None, None),
        (None, ("First / Brief", "Details"), None),
        (None, ("First", "Missing"), None),
        (None, None, "missing"),
        (None, None, "#deep-label"),
    ],
)
def test_missing_or_ambiguous(
    *,
    title: str | None,
    path: tuple[str, ...] | None,
    label: str | None,
) -> None:
    """Missing selections never fall back to another selection mode."""
    doc = publish_doctree(source=SOURCE)
    assert (
        len(find_sections(document=doc, title=title, path=path, label=label))
        != 1
    )
    with pytest.raises(
        expected_exception=ValueError, match="Expected one section"
    ):
        _ = select_section(document=doc, title=title, path=path, label=label)


@pytest.mark.parametrize(
    argnames=("title", "path", "label", "message"),
    argvalues=[
        (None, None, None, "exactly one"),
        ("First", ("First",), None, "exactly one"),
        ("First", None, "first", "exactly one"),
        (None, ("First",), "first", "exactly one"),
        ("First", ("First",), "first", "exactly one"),
        ("", None, None, "title must not be empty"),
        ("  ", None, None, "title must not be empty"),
        (None, (), None, "nonempty headings"),
        (None, ("First", ""), None, "nonempty headings"),
        (None, (" ",), None, "nonempty headings"),
        (None, None, "", "label must not be empty"),
        (None, None, "  ", "label must not be empty"),
    ],
)
def test_invalid_selection_modes(
    *,
    title: str | None,
    path: tuple[str, ...] | None,
    label: str | None,
    message: str,
) -> None:
    """Require one populated mode before matching any document content."""
    doc = publish_doctree(source=SOURCE)
    with pytest.raises(expected_exception=ValueError, match=message):
        _ = find_sections(document=doc, title=title, path=path, label=label)


@pytest.mark.parametrize(argnames="include_heading", argvalues=[False, True])
def test_copy_is_independent(*, include_heading: bool) -> None:
    """Copying keeps node structure, anchors, and metadata without
    mutation.
    """
    doc = publish_doctree(source=SOURCE, source_path="original.rst")
    part = select_section(document=doc, title="First")
    brief = select_section(document=part, label="stable-brief")
    details = select_section(document=brief, title="Details")
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
    part = select_section(document=doc, title="First")
    excluded = select_section(document=doc, title=selector)
    with pytest.raises(
        expected_exception=ValueError, match="must be descendants"
    ):
        _ = copy_section(
            section=part, include_heading=True, exclude_sections=(excluded,)
        )
