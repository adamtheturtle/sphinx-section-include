"""Expose parsed section inclusion as a Sphinx directive."""

import posixpath
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, override
from urllib.parse import urlsplit

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.application import Sphinx
from sphinx.errors import NoUri
from sphinx.util import docname_join
from sphinx.util.docutils import SphinxDirective

from sphinx_section_include.reader import read_document, resolve_source
from sphinx_section_include.sections import copy_section, select_section


def _prepare_nodes(
    *,
    directive: SphinxDirective,
    content: list[nodes.Node],
    source_docname: str,
) -> list[nodes.Node]:
    """Prefix copied targets and retain external reference origins."""
    container = nodes.container()
    container.extend(item=content)
    serial = directive.env.new_serialno(category="section-include")
    prefix = f"section-include-{serial}-"
    elements = list(container.findall(condition=nodes.Element))
    identities = {
        identity: prefix + identity
        for element in elements
        for identity in element["ids"]
    }
    names = {
        name: prefix + name
        for element in elements
        for name in element["names"]
    }
    for element in elements:
        element["ids"] = [identities[identity] for identity in element["ids"]]
        element["names"] = [names[name] for name in element["names"]]
        if bool(element["ids"]) or bool(element["names"]):
            directive.state.document.note_explicit_target(target=element)
        element.document = directive.state.document
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
        if (
            reference.get(key="reftype") == "ref"
            and reference["reftarget"] in names
        ):
            reference["reftarget"] = names[reference["reftarget"]]
        elif reference.get(key="reftype") == "doc":
            reference["reftarget"] = "/" + docname_join(
                basedocname=source_docname, docname=reference["reftarget"]
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
        target = reference["refid"]
        if target in identities:
            reference["refid"] = identities[target]
        else:
            del reference["refid"]
            _ = reference.setdefault(
                key="section_include_origin", failobj=source_docname
            )
            reference["section_include_anchor"] = target
    elif "refuri" in reference and _is_relative_uri(uri=reference["refuri"]):
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
    if not _is_relative_uri(uri=image["uri"]):
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
    image["uri"] = "/" + posixpath.normpath(
        path=posixpath.join(relative, str(object=image["uri"]))
    )


def resolve_included_references(
    app: Sphinx, doctree: nodes.document, docname: str
) -> None:
    """Resolve source links using the active builder's URI conventions."""
    for reference in doctree.findall(condition=nodes.reference):
        origin = reference.get(key="section_include_origin")
        if origin is None:
            continue
        try:
            base = app.builder.get_relative_uri(from_=docname, to=origin)
        except NoUri:
            reference.replace_self(new=reference.children)
            continue
        anchor = reference.get(key="section_include_anchor")
        if anchor is not None:
            reference["refuri"] = base + "#" + anchor
        else:
            # Keep paths relative to the original rendered document.

            parsed = urlsplit(url=str(object=reference["refuri"]))
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


class IncludeSection(SphinxDirective):
    """Include one exact section while preserving its document
    structure.
    """

    required_arguments = 1
    option_spec: ClassVar[dict[str, Callable[[str], Any]] | None] = {  # pyrefly: ignore[explicit-any]
        "section": directives.unchanged_required,
        "include-heading": directives.flag,
        "exclude-sections": directives.unchanged_required,
    }

    @override
    def run(self) -> list[nodes.Node]:
        """Read, select, and copy a section without rendering it to
        HTML.
        """
        if "section" not in self.options:
            raise self.error(message="include-section requires :section:")
        try:
            path = resolve_source(directive=self, source=self.arguments[0])
            document = read_document(directive=self, source=self.arguments[0])
            selected = select_section(
                document=document, selector=self.options["section"]
            )
            excluded = tuple(
                select_section(document=selected, selector=selector.strip())
                for selector in self.options.get(
                    "exclude-sections", ""
                ).splitlines()
                if bool(selector.strip())
            )
            content = copy_section(
                section=selected,
                include_heading="include-heading" in self.options,
                exclude_sections=excluded,
            )
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
