"""Select and copy parsed sections without imposing presentation
policy.
"""

from docutils import nodes


def find_sections(
    *, document: nodes.document | nodes.section, selector: str
) -> list[nodes.section]:
    """Find literal headings, heading paths, or standard RST labels.

    Literal headings take precedence over path or label syntax.
    """
    sections = list(document.findall(condition=nodes.section))
    literal = [
        section for section in sections if section[0].astext() == selector
    ]
    if bool(literal):
        return literal
    if selector.startswith("#"):
        label = nodes.fully_normalize_name(name=selector[1:])
        return [
            section
            for section in sections
            if label in section["names"] or label in section["ids"]
        ]
    parts = [part.strip() for part in selector.split(sep="/")]
    matches: list[nodes.section] = [
        section for section in sections if section[0].astext() == parts[0]
    ]
    for part in parts[1:]:
        matches = [
            child
            for section in matches
            for child in section.children
            if isinstance(child, nodes.section) and child[0].astext() == part
        ]
    return matches


def select_section(
    *, document: nodes.document | nodes.section, selector: str
) -> nodes.section:
    """Require exactly one matching section."""
    matches = find_sections(document=document, selector=selector)
    if len(matches) != 1:
        message = (
            f"Expected one section for {selector!r}, found {len(matches)}"
        )
        raise ValueError(message)
    return matches[0]


def copy_section(
    *,
    section: nodes.section,
    include_heading: bool = True,
    exclude_sections: tuple[nodes.section, ...] = (),
) -> list[nodes.Node]:
    """Copy a subtree, preserving headings, anchors, and source metadata.

    Exclusions must be resolved descendants of the selected section.
    The source tree is never modified.
    """
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
    return [copied] if include_heading else copied.children[1:]
