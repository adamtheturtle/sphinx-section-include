"""Read source documents through the active Sphinx directive context."""

from copy import copy
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import Parser
from docutils.transforms.references import (
    AnonymousHyperlinks,
    DanglingReferences,
    ExternalTargets,
    IndirectHyperlinks,
    InternalTargets,
    PropagateTargets,
    Substitutions,
)
from docutils.utils import new_document
from sphinx.transforms import DefaultSubstitutions
from sphinx.util.docutils import LoggingReporter, SphinxDirective


def resolve_source(*, directive: SphinxDirective, source: str) -> Path:
    """Resolve an RST source inside the Sphinx source directory."""
    root = Path(directive.env.srcdir).resolve()
    _relative, filename = directive.env.relfn2path(filename=source)
    path = Path(filename).resolve()
    if not path.is_relative_to(root) or path.suffix != ".rst":
        message = (
            "Section source must be an RST file within the source directory"
        )
        raise ValueError(message)
    current = Path(
        directive.env.doc2path(docname=directive.env.docname)
    ).resolve()
    if path == current:
        message = "A section include cannot include itself"
        raise ValueError(message)
    if not path.is_file():
        message = f"Section source does not exist: {source!r}"
        raise ValueError(message)
    return path


def read_document(
    *, directive: SphinxDirective, source: str, docname: str | None = None
) -> nodes.document:
    """Parse source content and record its transitive include dependencies.

    Registered directives, substitutions, and the caller's Sphinx configuration
    remain available. Source-relative includes use the source document's path.
    Temporary parsing context is restored even if parsing fails.
    """
    path = resolve_source(directive=directive, source=source)
    root = Path(directive.env.srcdir).resolve()
    parent = directive.state.document
    raw_ancestors = parent.get(key="_section_include_sources")
    ancestors: tuple[str, ...] = (
        () if raw_ancestors is None else raw_ancestors
    )
    if str(object=path) in ancestors:
        message = f"Circular section include involving {path.name!r}"
        raise ValueError(message)
    settings = copy(x=parent.settings)
    document = new_document(
        source_path=str(
            object=directive.env.doc2path(
                docname=directive.env.docname if docname is None else docname
            )
        ),
        settings=settings,
    )
    document.reporter = LoggingReporter.from_reporter(
        reporter=document.reporter
    )
    document["_section_include_sources"] = (*ancestors, str(object=path))
    relative = path.relative_to(root).as_posix()
    env = directive.env
    current = env.current_document
    source_docname = path.relative_to(root).with_suffix(suffix="").as_posix()
    context = copy(x=current)
    context.docname = source_docname if docname is None else docname
    env.note_dependency(filename=path)
    env.current_document = context
    try:
        text = "\n\n".join(
            part
            for part in (
                directive.config.rst_prolog or "",
                f".. include:: /{relative}",
                directive.config.rst_epilog or "",
            )
            if bool(part)
        )
        Parser().parse(inputstring=text, document=document)
        for transform in (
            DefaultSubstitutions,
            Substitutions,
            PropagateTargets,
            AnonymousHyperlinks,
            IndirectHyperlinks,
            ExternalTargets,
            InternalTargets,
            DanglingReferences,
        ):
            transform(document=document).apply()
    finally:
        env.current_document = current
        env.dependencies[current.docname].update(
            env.dependencies[context.docname]
        )
    return document
