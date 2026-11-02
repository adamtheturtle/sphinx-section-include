"""Read source documents through the active Sphinx directive context."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import copy
from dataclasses import dataclass
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
from sphinx.environment import BuildEnvironment
from sphinx.transforms import DefaultSubstitutions
from sphinx.util.docutils import LoggingReporter, SphinxDirective


@dataclass(frozen=True, kw_only=True)
class _Preparation:
    """A caller's transformation within one environment and scope."""

    environment: BuildEnvironment
    prepare: Callable[[nodes.document], None]


@dataclass(frozen=True, kw_only=True)
class _Source:
    """One prepared source, scoped to its consuming document."""

    environment: BuildEnvironment
    docname: str
    parsing_docname: str
    path: Path
    document: nodes.document
    preparation: _Preparation | None


_sources: ContextVar[tuple[_Source, ...]] = ContextVar(
    "section_sources", default=()
)
_preparations: ContextVar[tuple[_Preparation, ...]] = ContextVar(
    "section_preparations", default=()
)


def _preparation_for(*, environment: BuildEnvironment) -> _Preparation | None:
    """Use the innermost preparation for this environment."""
    for preparation in reversed(_preparations.get()):
        if preparation.environment is environment:
            return preparation
    return None


@contextmanager
def prepare_sources(
    *,
    directive: SphinxDirective,
    prepare: Callable[[nodes.document], None],
) -> Generator[None]:
    """Prepare freshly read section sources before selection or copying.

    The callback mutates each parsed document in place. It applies to reads in
    this Sphinx environment for the lifetime of this context, including sources
    read by nested section includes. Nested preparations replace the outer
    callback for their environment and restore it on success or failure.
    Prepared trees are reused only within the same preparation scope.
    """
    token = _preparations.set(
        (
            *_preparations.get(),
            _Preparation(environment=directive.env, prepare=prepare),
        )
    )
    try:
        yield
    finally:
        _preparations.reset(token)


@contextmanager
def section_source(
    *, directive: SphinxDirective, source: str, docname: str | None = None
) -> Generator[nodes.document]:
    """Share one parsed source with includes executed inside this context.

    The yielded document may be prepared before parsing the including content.
    Only this environment and consuming document reuse it. Leaving the context,
    including after an exception, restores any surrounding source context.
    Nothing is retained between builds or template contexts.
    """
    path = resolve_source(directive=directive, source=source)
    preparation = _preparation_for(environment=directive.env)
    document = read_document(
        directive=directive, source=source, docname=docname
    )
    token = _sources.set(
        (
            *_sources.get(),
            _Source(
                environment=directive.env,
                docname=directive.env.docname,
                parsing_docname=(
                    path.relative_to(Path(directive.env.srcdir).resolve())
                    .with_suffix(suffix="")
                    .as_posix()
                    if docname is None
                    else docname
                ),
                path=path,
                document=document,
                preparation=preparation,
            ),
        )
    )
    try:
        yield document
    finally:
        _sources.reset(token)


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
    ancestors = tuple[str, ...](
        parent.get(key="_section_include_sources", failobj=())
    )
    if str(object=path) in ancestors:
        message = f"Circular section include involving {path.name!r}"
        raise ValueError(message)
    preparation = _preparation_for(environment=directive.env)
    for prepared in reversed(_sources.get()):
        if prepared.preparation is not preparation:
            continue
        if (
            prepared.environment is directive.env
            and prepared.docname == directive.env.docname
            and prepared.path == path
            and (docname is None or docname == prepared.parsing_docname)
        ):
            directive.env.note_dependency(filename=path)
            return prepared.document
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
    if preparation is not None:
        preparation.prepare(document)
    return document
