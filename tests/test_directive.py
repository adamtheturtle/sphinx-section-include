"""Section inclusion works across source directories and output
builders.
"""

import base64
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from docutils import nodes
from sphinx.errors import NoUri
from sphinx.testing.util import SphinxTestApp

from sphinx_section_include.directive import resolve_included_references


def write_project(*, root: Path, directive: str) -> None:
    """Create an independent Sphinx consumer with nested source files."""
    files = {
        ("conf.py"): (
            "extensions = ['sphinx_section_include']\nproject = 'Example'\n"
        ),
        ("index.rst"): (
            "Index\n=====\n\n.. toctree::\n\n   manual/source\n   manual/o"
            "ther\n   overview\n"
        ),
        "manual/source.rst": textwrap.dedent(
            text="""\
            Source manual
            =============

            Parent
            ------

            .. _configuration:

            Configuration
            ~~~~~~~~~~~~~

            .. include:: details.txt

            See Details_ and Outside_.
            See :ref:`configuration` and :doc:`other`.
            Visit `external <https://example.com/>`_.
            Download `asset <asset.txt>`_.

            .. image:: pixel.png

            Details
            ^^^^^^^

            Local details.

            Outside
            ~~~~~~~

            Other source content.
            """
        ),
        ("manual/details.txt"): (
            "Included instructions.\n\n.. code-block:: text\n\n   whites"
            "pace   matters\n"
        ),
        ("manual/other.rst"): (
            "Other manual\n============\n\nMore information.\n"
        ),
        "manual/asset.txt": "Download content.\n",
        "overview.rst": "Overview\n========\n\n" + directive,
    }
    root.mkdir(parents=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(data=content)
    _ = (root / "manual/pixel.png").write_bytes(
        data=base64.b64decode(
            s="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR"
            "42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII="
        )
    )


@pytest.mark.parametrize(
    argnames="buildername", argvalues=["html", "dirhtml", "text", "latex"]
)
@pytest.mark.parametrize(argnames="include_heading", argvalues=[False, True])
def test_include_preserves_content_and_links(
    *,
    make_app: Callable[..., SphinxTestApp],
    tmp_path: Path,
    buildername: str,
    include_heading: bool,
) -> None:
    """Included content, references, and resources retain their origin."""
    directive = (
        ".. include-section:: manual/source.rst\n"
        "   :section: Parent / Configuration\n"
    )
    if include_heading:
        directive += "   :include-heading:\n"
    source = tmp_path / "source"
    write_project(root=source, directive=directive)
    app = make_app(
        srcdir=source, buildername=buildername, exception_on_warning=True
    )
    app.build()
    assert app.statuscode == 0
    assert app.warning.getvalue() == ""
    tree = app.env.get_doctree(docname="overview")
    assert "Included instructions." in tree.astext()
    assert "Other source content." not in tree.astext()
    assert len(list(tree.findall(condition=nodes.section))) == (
        3 if include_heading else 2
    )
    if buildername in {"html", "dirhtml"}:
        filename = (
            "overview.html" if buildername == "html" else "overview/index.html"
        )
        soup = BeautifulSoup(
            markup=(Path(app.outdir) / filename).read_text(),
            features="html.parser",
        )
        content = soup.select_one(selector="div.body")
        assert content is not None
        links = {
            a.get_text(): str(object=a.get(key="href"))
            for a in content.select(selector="a[href]")
        }
        assert links["Details"].startswith("#section-include-")
        assert links["Outside"] == (
            "manual/source.html#outside"
            if buildername == "html"
            else "../manual/source/#outside"
        )
        assert links["Other manual"] == (
            "manual/other.html"
            if buildername == "html"
            else "../manual/other/"
        )
        assert links["external"] == "https://example.com/"
        assert links["asset"] == (
            "manual/asset.txt"
            if buildername == "html"
            else "../manual/source/asset.txt"
        )
        image = content.select_one(selector="img")
        assert image is not None
        assert "pixel.png" in str(object=image["src"])
    dependencies = {
        Path(path).as_posix() for path in app.env.dependencies["overview"]
    }
    assert any(path.endswith("manual/source.rst") for path in dependencies)
    assert any(path.endswith("manual/details.txt") for path in dependencies)


def test_repeated_inclusion_namespaces_targets(
    *, make_app: Callable[..., SphinxTestApp], tmp_path: Path
) -> None:
    """Repeated excerpts keep separate anchors and local references."""
    directive = (
        ".. include-section:: manual/source.rst\n   :section: #co"
        "nfiguration\n   :include-heading:\n\n"
    )
    source = tmp_path / "source"
    write_project(root=source, directive=directive + directive)
    app = make_app(srcdir=source, exception_on_warning=True)
    app.build()
    assert app.warning.getvalue() == ""
    soup = BeautifulSoup(
        markup=(Path(app.outdir) / "overview.html").read_text(),
        features="html.parser",
    )
    ids = [node["id"] for node in soup.select(selector="[id]")]
    assert len(ids) == len(set(ids))
    for number in (0, 1):
        assert (
            soup.select_one(
                selector=f"#section-include-{number}-configuration"
            )
            is not None
        )


def test_exclusions_and_incremental_dependencies(
    *, make_app: Callable[..., SphinxTestApp], tmp_path: Path
) -> None:
    """Changing only an included file refreshes an excerpt and its
    exclusions.
    """
    source = tmp_path / "source"
    write_project(
        root=source,
        directive=(
            ".. include-section:: manual/source.rst\n   :section: #co"
            "nfiguration\n   :exclude-sections: Details\n"
        ),
    )
    app = make_app(srcdir=source, exception_on_warning=True)
    app.build()
    output = Path(app.outdir) / "overview.html"
    assert "Included instructions." in output.read_text()
    assert "Local details." not in output.read_text()
    _ = (source / "manual/details.txt").write_text(
        data="Updated instructions.\n"
    )
    app.build()
    assert "Updated instructions." in output.read_text()
    assert app.warning.getvalue() == ""


@pytest.mark.parametrize(
    argnames=("source_name", "options", "message"),
    argvalues=[
        ("../outside.rst", ":section: Parent", "within the source directory"),
        (
            "manual/source.txt",
            ":section: Parent",
            "within the source directory",
        ),
        ("overview.rst", ":section: Overview", "cannot include itself"),
        ("missing.rst", ":section: Parent", "does not exist"),
        ("manual/source.rst", "", "requires :section:"),
        ("manual/source.rst", ":section: Missing", "Expected one section"),
        (
            "manual/source.rst",
            ":section: #configuration\n:exclude-sections: Missing",
            "Expected one section",
        ),
        (
            "manual/source.rst",
            ":section: #configuration\n:exclude-sections: #configuration",
            "must be descendants",
        ),
    ],
)
def test_invalid_inputs_report_errors(
    *,
    make_app: Callable[..., SphinxTestApp],
    tmp_path: Path,
    source_name: str,
    options: str,
    message: str,
) -> None:
    """Invalid selections produce explicit build errors."""
    directive = f".. include-section:: {source_name}\n" + "".join(
        "   " + line + "\n" for line in options.splitlines()
    )
    source = tmp_path / "source"
    write_project(root=source, directive=directive)
    app = make_app(srcdir=source)
    app.build()
    assert message in app.warning.getvalue()


def test_circular_inclusion_reports_error(
    *, make_app: Callable[..., SphinxTestApp], tmp_path: Path
) -> None:
    """Cycles are rejected without unbounded parser recursion."""
    source = tmp_path / "source"
    write_project(
        root=source,
        directive=(
            ".. include-section:: manual/source.rst\n   :section: Parent\n"
        ),
    )
    _ = (source / "manual/source.rst").write_text(
        data="Source\n======\n\nParent\n------\n\n.. include-section:: othe"
        "r.rst\n   :section: Other\n"
    )
    _ = (source / "manual/other.rst").write_text(
        data="Other\n=====\n\n.. include-section:: source.rst\n   :sectio"
        "n: Parent\n"
    )
    app = make_app(srcdir=source)
    app.build()
    assert "Circular section include" in app.warning.getvalue()


def test_external_resources_and_cross_references(
    *, make_app: Callable[..., SphinxTestApp], tmp_path: Path
) -> None:
    """Remote resources and references outside an excerpt retain their
    targets.
    """
    source = tmp_path / "source"
    write_project(
        root=source,
        directive=(
            ".. include-section:: manual/source.rst\n"
            "   :section: #configuration\n"
        ),
    )
    path = source / "manual/source.rst"
    _ = path.write_text(
        data=path.read_text()
        .replace(
            "See Details_ and Outside_.",
            "See Details_ and Outside_.\n\n"
            "See :ref:`outside-label` and :py:func:`unknown_function`.\n\n"
            ".. image:: https://example.com/remote.png\n\n"
            "Link `query <?view=all>`_.",
        )
        .replace("Outside\n~~~~~~~", ".. _outside-label:\n\nOutside\n~~~~~~~")
    )
    app = make_app(srcdir=source, exception_on_warning=True)
    app.build()
    html = (Path(app.outdir) / "overview.html").read_text()
    assert 'src="https://example.com/remote.png"' in html
    assert 'href="manual/source.html#outside-label"' in html
    assert 'href="manual/source.html?view=all"' in html
    assert "unknown_function" in html
    assert app.warning.getvalue() == ""


def test_builder_without_document_uris(
    *,
    make_app: Callable[..., SphinxTestApp],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A builder without document links keeps the readable reference
    content.
    """
    source = tmp_path / "source"
    write_project(
        root=source,
        directive=(
            ".. include-section:: manual/source.rst\n"
            "   :section: #configuration\n"
        ),
    )
    app = make_app(srcdir=source, exception_on_warning=True)
    app.build()

    def no_uri(*, from_: str, to: str) -> str:
        """Represent a builder that cannot link to another document."""
        raise NoUri(from_, to)

    monkeypatch.setattr(
        target=app.builder, name="get_relative_uri", value=no_uri
    )
    tree = app.env.get_doctree(docname="overview")
    resolve_included_references(app=app, doctree=tree, docname="overview")
    assert "Outside" in tree.astext()
    assert not any(
        node.get(key="section_include_origin")
        for node in tree.findall(condition=nodes.reference)
    )


def test_nested_excerpts_keep_their_reference_origins(
    *, make_app: Callable[..., SphinxTestApp], tmp_path: Path
) -> None:
    """Wrapping an excerpt again preserves links to its original
    document.
    """
    source = tmp_path / "source"
    write_project(
        root=source,
        directive=(
            ".. include-section:: manual/source.rst\n"
            "   :section: Parent / Configuration\n"
        ),
    )
    _ = (source / "manual/other.rst").write_text(
        data="Other manual\n============\n\n"
        "Excerpt\n-------\n\nSee Neighbor_.\n\n"
        "Link `folder <assets/>`_.\n\n"
        "Neighbor\n--------\n\nNeighboring content.\n"
    )
    path = source / "manual/source.rst"
    _ = path.write_text(
        data=path.read_text().replace(
            "See Details_ and Outside_.",
            "See Details_ and Outside_.\n\n"
            ".. include-section:: other.rst\n   :section: Excerpt\n",
        )
    )
    app = make_app(srcdir=source, exception_on_warning=True)
    app.build()
    html = (Path(app.outdir) / "overview.html").read_text()
    assert 'href="manual/other.html#neighbor"' in html
    assert 'href="manual/assets/"' in html
    assert "Neighboring content." not in html
    assert app.warning.getvalue() == ""
