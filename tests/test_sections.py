"""Selection and copying preserve parsed document semantics."""

from typing import Literal

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
@pytest.mark.parametrize(
    argnames="heading_style", argvalues=["section", "rubric"]
)
def test_copy_is_independent(
    *, include_heading: bool, heading_style: Literal["section", "rubric"]
) -> None:
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
        heading_style=heading_style,
    )
    container = nodes.container()
    container.extend(item=content)
    assert "Nested details." not in container.astext()
    assert "A literal slash heading." in container.astext()
    assert part.pformat() == original
    heading_type = nodes.rubric if heading_style == "rubric" else nodes.section
    assert all(
        node.source == "original.rst"
        for node in container.findall(condition=heading_type)
    )
    if heading_style == "rubric":
        assert not bool(list(container.findall(condition=nodes.section)))
        assert [
            node.astext() for node in container.findall(condition=nodes.rubric)
        ] == [
            *(["First"] if include_heading else []),
            "Brief",
            "Brief / Details",
            "Deep / nested",
            "#stable-brief",
        ]
    if include_heading:
        assert isinstance(content[0], heading_type)
        assert content[0]["ids"] == part["ids"]
    else:
        assert (
            next(container.findall(condition=nodes.rubric)).astext()
            if heading_style == "rubric"
            else next(container.findall(condition=nodes.section))[0].astext()
        ) == "Brief"
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


def test_rubrics_preserve_heading_markup_targets_and_locations() -> None:
    """Flatten copied headings without losing inline markup or targets."""
    doc = publish_doctree(
        source=(
            "Manual\n======\n\nPart *one*\n----------\n\nContent.\n\n"
            "Another part\n------------\n\nOther content.\n"
        ),
        source_path="original.rst",
    )
    part = select_section(document=doc, title="Part one")
    title = part[0]
    assert isinstance(title, nodes.title)
    title["ids"] = ["title-id"]
    title["names"] = ["title-name"]
    title["classes"] = ["title-class"]
    title["backrefs"] = ["title-backref"]
    part["classes"] = ["section-class"]
    part["backrefs"] = ["section-backref"]
    original = doc.pformat()
    (rubric, body) = copy_section(section=part, heading_style="rubric")
    assert isinstance(rubric, nodes.rubric)
    assert rubric.astext() == "Part one"
    assert len(list(rubric.findall(condition=nodes.emphasis))) == 1
    assert rubric["ids"] == [*part["ids"], "title-id"]
    assert rubric["names"] == [*part["names"], "title-name"]
    assert rubric["classes"] == ["section-class", "title-class"]
    assert rubric["backrefs"] == ["section-backref", "title-backref"]
    assert rubric.rawsource == title.rawsource
    assert rubric.source == title.source == "original.rst"
    assert rubric.line == title.line
    assert body.astext() == "Content."
    assert doc.pformat() == original
