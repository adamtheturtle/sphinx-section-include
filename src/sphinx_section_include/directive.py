"""Expose parsed section inclusion as a Sphinx directive."""

import json
import posixpath
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import ClassVar, Literal, TypeGuard, override
from urllib.parse import urlsplit

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.application import Sphinx
from sphinx.errors import NoUri
from sphinx.util import docname_join
from sphinx.util.docutils import SphinxDirective

from sphinx_section_include._types import (
    is_heading_paths,
    is_list,
    is_string_list,
    is_string_tuple,
)
from sphinx_section_include.reader import read_document, resolve_source
from sphinx_section_include.sections import copy_section, select_section
from sphinx_section_include.validation import validate_content


def _prepare_nodes(
    *,
    directive: SphinxDirective,
    content: list[nodes.Node],
    source_docname: str,
) -> list[nodes.Node]:
    """Prefix copied targets and retain external reference origins."""
    container = nodes.container()
    container.extend(item=content)
    for node in container.findall():
        node.document = directive.state.document
    serial = directive.env.new_serialno(category="section-include")
    document_id = directive.env.docname.encode(encoding="utf-8").hex()
    prefix = f"section-include-{document_id}-{serial}-"
    elements: list[tuple[nodes.Element, list[str], list[str]]] = []
    for element in container.findall(condition=nodes.Element):
        ids: object = element["ids"]
        element_names: object = element["names"]
        assert is_string_list(ids)
        assert is_string_list(element_names)
        elements.append((element, ids, element_names))
    identities = {
        identity: prefix + identity
        for _, ids, _ in elements
        for identity in ids
    }
    names = {
        name: prefix + name
        for _, _, element_names in elements
        for name in element_names
    }
    for element, ids, element_names in elements:
        element["ids"] = [identities[identity] for identity in ids]
        element["names"] = [names[name] for name in element_names]
        if bool(ids) or bool(element_names):
            directive.state.document.note_explicit_target(target=element)
        if isinstance(element, addnodes.pending_xref):
            _prepare_cross_reference(
                reference=element,
                names=names,
                source_docname=source_docname,
                docname=directive.env.docname,
            )
        if isinstance(element, nodes.reference):
            _prepare_reference(
                reference=element,
                identities=identities,
                source_docname=source_docname,
            )
        if isinstance(element, nodes.image):
            _prepare_image(
                image=element,
                directive=directive,
                source_docname=source_docname,
            )
    return container.children


def _prepare_cross_reference(
    *,
    reference: addnodes.pending_xref,
    names: dict[str, str],
    source_docname: str,
    docname: str,
) -> None:
    """Keep Sphinx roles tied to their selected target or original
    document.
    """
    if reference.get(key="refdomain") == "std":
        reference_type: object = reference.get(key="reftype")
        if isinstance(reference_type, str) and reference_type in {
            "ref",
            "doc",
        }:
            target: object = reference["reftarget"]
            assert isinstance(target, str)
            if reference_type == "ref" and target in names:
                reference["reftarget"] = names[target]
            elif reference_type == "doc":
                reference["reftarget"] = "/" + docname_join(
                    basedocname=source_docname, docname=target
                )
    reference["refdoc"] = docname


def _is_relative_uri(*, uri: str) -> bool:
    """Recognize local links without schemes, hosts, or rooted paths."""
    parsed = urlsplit(url=uri)
    return (
        not bool(parsed.scheme)
        and not bool(parsed.netloc)
        and not parsed.path.startswith("/")
    )


def _prepare_reference(
    *,
    reference: nodes.reference,
    identities: dict[str, str],
    source_docname: str,
) -> None:
    """Distinguish anchors inside the excerpt from links to its source."""
    if "refid" in reference:
        target: object = reference["refid"]
        assert isinstance(target, str)
        if target in identities:
            reference["refid"] = identities[target]
        else:
            del reference["refid"]
            _ = reference.setdefault(
                key="section_include_origin", failobj=source_docname
            )
            reference["section_include_anchor"] = target
    elif "refuri" in reference:
        uri: object = reference["refuri"]
        assert isinstance(uri, str)
        if _is_relative_uri(uri=uri):
            _ = reference.setdefault(
                key="section_include_origin", failobj=source_docname
            )


def _prepare_image(
    *,
    image: nodes.image,
    directive: SphinxDirective,
    source_docname: str,
) -> None:
    """Resolve local image paths before the caller collects image
    assets.
    """
    uri: object = image["uri"]
    assert isinstance(uri, str)
    if not _is_relative_uri(uri=uri):
        return
    origin = Path(
        image.source
        if image.source is not None
        else directive.env.doc2path(docname=source_docname)
    )
    relative = (
        origin.parent.resolve()
        .relative_to(Path(directive.env.srcdir).resolve())
        .as_posix()
    )
    image["uri"] = "/" + posixpath.normpath(path=posixpath.join(relative, uri))


def resolve_included_references(
    app: Sphinx, doctree: nodes.document, docname: str
) -> None:
    """Resolve source links using the active builder's URI conventions."""
    for reference in doctree.findall(condition=nodes.reference):
        origin: object = reference.get(key="section_include_origin")
        if origin is None:
            continue
        assert isinstance(origin, str)
        try:
            base = app.builder.get_relative_uri(from_=docname, to=origin)
        except NoUri:
            reference.replace_self(new=reference.children)
            continue
        anchor: object = reference.get(key="section_include_anchor")
        if anchor is not None:
            assert isinstance(anchor, str)
            reference["refuri"] = base + "#" + anchor
        else:
            # Keep paths relative to the original rendered document.

            uri: object = reference["refuri"]
            assert isinstance(uri, str)
            parsed = urlsplit(url=uri)
            path = (
                posixpath.normpath(
                    path=posixpath.join(posixpath.dirname(base), parsed.path)
                )
                if bool(parsed.path)
                else base
            )
            if parsed.path.endswith("/") and not path.endswith("/"):
                path += "/"
            reference["refuri"] = parsed._replace(path=path).geturl()


def _heading_path(argument: str | None, /) -> tuple[str, ...]:
    """Read one literal heading component per physical option line."""
    value = argument if argument is not None else ""
    if not bool(value.strip()):
        message = "Section path option must not be empty"
        raise ValueError(message)
    return tuple(line.strip() for line in value.strip().splitlines())


def _excluded_paths(argument: str | None, /) -> tuple[tuple[str, ...], ...]:
    """Read one JSON array per excluded heading path."""
    value = argument if argument is not None else ""
    if not bool(value.strip()):
        message = "Section path option must not be empty"
        raise ValueError(message)
    paths: list[tuple[str, ...]] = []
    for line in value.strip().splitlines():
        decoded: object = json.loads(s=line)
        if is_list(decoded):
            components: list[object] = decoded
        else:
            message = (
                "Each excluded section path must be a JSON array "
                "of nonempty strings"
            )
            raise TypeError(message)
        path: list[str] = []
        for component in components:
            if not isinstance(component, str) or not bool(component.strip()):
                message = (
                    "Each excluded section path must be a JSON array "
                    "of nonempty strings"
                )
                raise ValueError(message)
            path.append(component)
        if not bool(path):
            message = "Excluded section paths must not be empty"
            raise ValueError(message)
        paths.append(tuple(path))
    return tuple(paths)


def _is_heading_style(
    value: object, /
) -> TypeGuard[Literal["section", "rubric"]]:
    """Identify a heading style accepted by the directive."""
    return isinstance(value, str) and value in {"section", "rubric"}


class IncludeSection(SphinxDirective):
    """Include one exact section while preserving its document
    structure.
    """

    required_arguments = 1
    option_spec: ClassVar[dict[str, Callable[[str], object]] | None] = {
        "section": directives.unchanged_required,
        "section-path": _heading_path,
        "section-label": directives.unchanged_required,
        "include-heading": directives.flag,
        "heading-style": partial(
            directives.choice, values=("section", "rubric")
        ),
        "exclude-sections": directives.unchanged_required,
        "exclude-section-paths": _excluded_paths,
        "exclude-section-labels": directives.unchanged_required,
    }

    @override
    def run(self) -> list[nodes.Node]:
        """Read, select, and copy a section without rendering it to
        HTML.
        """
        if (
            sum(
                name in self.options
                for name in ("section", "section-path", "section-label")
            )
            != 1
        ):
            raise self.error(
                message=(
                    "include-section requires exactly one of :section:, "
                    ":section-path:, or :section-label:"
                )
            )
        try:
            path = resolve_source(directive=self, source=self.arguments[0])
            document = read_document(directive=self, source=self.arguments[0])
            title: object = self.options.get("section")
            heading_path: object = self.options.get("section-path")
            label: object = self.options.get("section-label")
            assert title is None or isinstance(title, str)
            assert heading_path is None or is_string_tuple(heading_path)
            assert label is None or isinstance(label, str)
            selected = select_section(
                document=document, title=title, path=heading_path, label=label
            )
            excluded_titles: object = self.options.get("exclude-sections", "")
            excluded_labels: object = self.options.get(
                "exclude-section-labels", ""
            )
            excluded_paths: object = self.options.get(
                "exclude-section-paths", ()
            )
            heading_style: object = self.options.get(
                "heading-style", "section"
            )
            assert isinstance(excluded_titles, str)
            assert isinstance(excluded_labels, str)
            assert is_heading_paths(excluded_paths)
            assert _is_heading_style(heading_style)
            excluded = (
                tuple(
                    select_section(document=selected, title=title.strip())
                    for title in excluded_titles.splitlines()
                    if bool(title.strip())
                )
                + tuple(
                    select_section(document=selected, label=label.strip())
                    for label in excluded_labels.splitlines()
                    if bool(label.strip())
                )
                + tuple(
                    select_section(document=selected, path=path)
                    for path in excluded_paths
                )
            )
            content = copy_section(
                section=selected,
                include_heading="include-heading" in self.options,
                exclude_sections=excluded,
                heading_style=heading_style,
            )
            validate_content(directive=self, content=content)
            return _prepare_nodes(
                directive=self,
                content=content,
                source_docname=path.relative_to(
                    Path(self.env.srcdir).resolve()
                )
                .with_suffix(suffix="")
                .as_posix(),
            )
        except ValueError as error:
            raise self.error(message=str(object=error)) from error
