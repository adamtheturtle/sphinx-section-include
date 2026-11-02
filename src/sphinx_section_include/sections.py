"""Select and copy parsed document sections."""

from typing import Literal

from docutils import nodes
from docutils.parsers.rst import directives


def find_sections(
    *,
    document: nodes.document | nodes.section,
    title: str | None = None,
    path: tuple[str, ...] | None = None,
    label: str | None = None,
) -> list[nodes.section]:
    """Find sections using exactly one explicit selection mode.

    Titles and path components are literal text, including slash and hash
    characters. Labels use Docutils' native name normalization.
    """
    if sum(value is not None for value in (title, path, label)) != 1:
        message = "Specify exactly one of title, path, or label"
        raise ValueError(message)
    sections = list(document.findall(condition=nodes.section))
    if title is not None:
        if not bool(title.strip()):
            message = "Section title must not be empty"
            raise ValueError(message)
        return [
            section for section in sections if section[0].astext() == title
        ]
    if label is not None:
        if not bool(label.strip()):
            message = "Section label must not be empty"
            raise ValueError(message)
        name = nodes.fully_normalize_name(name=label)
        return [
            section
            for section in sections
            if name in section["names"] or name in section["ids"]
        ]
    assert path is not None
    if not bool(path) or any(
        not bool(component.strip()) for component in path
    ):
        message = "Section path must contain nonempty headings"
        raise ValueError(message)
    matches: list[nodes.section] = [
        section for section in sections if section[0].astext() == path[0]
    ]
    for component in path[1:]:
        matches = [
            child
            for section in matches
            for child in section.children
            if isinstance(child, nodes.section)
            and child[0].astext() == component
        ]
    return matches


def select_section(
    *,
    document: nodes.document | nodes.section,
    title: str | None = None,
    path: tuple[str, ...] | None = None,
    label: str | None = None,
) -> nodes.section:
    """Require exactly one section for an explicit title, path, or
    label.
    """
    matches = find_sections(
        document=document, title=title, path=path, label=label
    )
    if len(matches) != 1:
        message = (
            f"Expected one section for title={title!r}, path={path!r}, "
            f"label={label!r}, found {len(matches)}"
        )
        raise ValueError(message)
    return matches[0]


def copy_section(
    *,
    section: nodes.section,
    include_heading: bool = True,
    exclude_sections: tuple[nodes.section, ...] = (),
    heading_style: Literal["section", "rubric"] = "section",
) -> list[nodes.Node]:
    """Copy a subtree, preserving headings, anchors, and source metadata.

    Exclusions must be resolved descendants of the selected section.
    The source tree is never modified. Rubric style turns every included
    section heading into an informal heading outside the section hierarchy.
    """
    style = directives.choice(
        argument=heading_style, values=("section", "rubric")
    )
    originals = list(section.findall(condition=nodes.section))
    identities = {id(node) for node in originals if node is not section}
    if any(id(node) not in identities for node in exclude_sections):
        message = "Excluded sections must be descendants of the selection"
        raise ValueError(message)
    copied = section.deepcopy()
    copies = list(copied.findall(condition=nodes.section))
    excluded = {id(node) for node in exclude_sections}
    for original, target in zip(originals, copies, strict=True):
        if id(original) in excluded:
            assert target.parent is not None
            _ = target.parent.remove(item=target)
    content: list[nodes.Node] = (
        [copied] if include_heading else copied.children[1:]
    )
    if style == "rubric":
        return _rubric_headings(content=content)
    return content


def _rubric_headings(*, content: list[nodes.Node]) -> list[nodes.Node]:
    """Replace copied sections with native rubric headings and their
    bodies.
    """
    container = nodes.container()
    container.extend(item=content)
    for section in list(container.findall(condition=nodes.section)):
        title = section[0]
        assert isinstance(title, nodes.title)
        rubric = nodes.rubric(
            title.rawsource,
            "",
            *title.children,
            **{**title.attributes, **section.attributes},
        )
        for attribute in ("ids", "names", "classes", "dupnames", "backrefs"):
            values: list[str] = [
                *section.get(key=attribute, failobj=[]),
                *title.get(key=attribute, failobj=[]),
            ]
            rubric[attribute] = list(dict.fromkeys(values))
        rubric.source = title.source
        rubric.line = title.line
        section.replace_self(new=[rubric, *section.children[1:]])
    return container.children
