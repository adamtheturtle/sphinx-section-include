Extension API
=============

``read_document`` parses an RST source using the active Sphinx environment and records its include dependencies.
``find_sections`` and ``select_section`` select headings, heading paths, or labels.
``copy_section`` copies a selection without changing its source tree.

Explicit section selection
--------------------------

Pass exactly one of ``title``, ``path``, or ``label`` to ``find_sections`` or ``select_section``.
For example, ``select_section(document=document, title="Input / output")`` selects that literal heading, while ``path=("Q1", "Input / output")`` selects it directly beneath ``Q1``.
``label="stable-prompt"`` selects the section carrying that RST label, using Docutils name normalization.
Titles and path components are exact, case-sensitive text.
``/`` and ``#`` have no special meaning.
The first path component may occur at any depth in the supplied document or section.
Later components must be direct child headings.
``find_sections`` returns all matches.
``select_section`` rejects missing or ambiguous matches.
An empty selector, or more than one mode, is an error.

The directive uses exactly one corresponding option:

.. code-block:: rst

   .. include-section:: manual.rst
      :section-path:
         Q1
         Input / output

Use ``:section: Input / output`` to select the literal heading anywhere in the source, or ``:section-label: stable-prompt`` for a label.
Do not prefix labels with ``#``.

Exclusions
----------

Exclusions must be descendants of the selected section.
These options can be combined:

* ``:exclude-sections:`` lists one literal heading per line.
* ``:exclude-section-labels:`` lists one RST label per line.
* ``:exclude-section-paths:`` lists one JSON array of literal heading components per line.

For example:

.. code-block:: rst

   .. include-section:: manual.rst
      :section: Q1
      :exclude-sections:
         Input / output
         #Examples
      :exclude-section-labels: internal-details
      :exclude-section-paths:
         ["Prompt", "Follow up questions"]
         ["Discussion / API", "Examples"]

Every exclusion must resolve to exactly one descendant.
The Python ``copy_section`` function accepts these already-resolved nodes in ``exclude_sections``.

Heading presentation
--------------------

By default, included headings remain ordinary document sections.
Use ``:heading-style: rubric`` to turn every included section heading into a Docutils rubric: an informal heading outside the document's section hierarchy and table of contents.
This is useful for excerpts inside disclosures, admonitions, or other containers.

.. code-block:: rst

   .. include-section:: manual.rst
      :section: Configuration
      :include-heading:
      :heading-style: rubric

``:include-heading:`` still controls whether the selected section's own heading appears.
Descendant headings use the chosen style whether or not that heading is included.
Rubric mode preserves inline heading formatting, target IDs and names, source locations, and references without changing the source document.
Both styles use native Docutils nodes and work with HTML and non-HTML builders.
The only supported styles are ``section`` and ``rubric``.

The Python API accepts ``copy_section(section=section, heading_style="rubric")`` with the same behavior.
Copying never registers targets in the source document.
The directive prefixes copied targets and registers them in the consuming document after applying the selected heading style.

Preparing a source once
-----------------------

Use ``section_source`` when several ``include-section`` directives share a prepared source:

.. code-block:: python

   """Render a directive's contents against a single prepared source."""

   from docutils import nodes
   from sphinx.util.docutils import SphinxDirective

   from sphinx_section_include import section_source

   __all__ = ["render_contents"]


   def render_contents(*, directive: SphinxDirective) -> list[nodes.Node]:
       """Share the source only while the including content is parsed."""
       container = nodes.container()
       with section_source(directive=directive, source="manual.rst"):
           _ = directive.state.nested_parse(
               block=directive.content,
               input_offset=directive.content_offset,
               node=container,
           )
       return container.children

The context manager yields the parsed document, which a consumer may prepare before parsing its contents.
Includes copy that tree without mutating it.
Reuse is limited to the current Sphinx environment, consuming document, and explicit context lifetime.
Nested contexts restore their surrounding context even after an exception.
Set a template context before entering.
Leave before selecting another context.
No parsed source is cached between builds or across template contexts.
An explicit ``docname`` selects a parsing context and reuses the source only when that context matches.
RST sources must remain inside the Sphinx source directory, and recursive includes remain errors.
Use ``section_source(..., docname=directive.env.docname)`` when extension collectors should attribute parsed content to the consuming document.
Reference and resource origins remain tied to the selected source.

Scoped source preparation
-------------------------

Use ``prepare_sources`` to apply a caller-supplied callback before section selection and copying.
The callback receives a parsed ``docutils.nodes.document`` positionally and mutates it in place.
It runs for freshly loaded sources reached through ``read_document``, ``section_source``, and ``include-section`` while the context is active in that Sphinx environment.
Ordinary Sphinx source parsing is unaffected.

.. code-block:: python

   """Apply a local presentation rule to section sources."""

   from docutils import nodes
   from sphinx.util.docutils import SphinxDirective

   from sphinx_section_include import prepare_sources, section_source

   __all__ = ["render_prepared"]


   def prepare_document(document: nodes.document, /) -> None:
       """Mark code examples using this consumer's presentation rule."""
       for example in document.findall(condition=nodes.literal_block):
           if "prepared-example" not in example["classes"]:
               example["classes"].append("prepared-example")


   def render_prepared(*, directive: SphinxDirective) -> list[nodes.Node]:
       """Prepare primary and additional section sources within one scope."""
       container = nodes.container()
       with (
           prepare_sources(directive=directive, prepare=prepare_document),
           section_source(directive=directive, source="manual.rst"),
       ):
           _ = directive.state.nested_parse(
               block=directive.content,
               input_offset=directive.content_offset,
               node=container,
           )
       return container.children

Repeated reads of a tree shared by ``section_source`` reuse its prepared result without applying the callback again.
Trees prepared in another scope are not reused, even if that scope used the same callback function.
Each nested preparation replaces its environment's outer callback and restores it after success or failure.
Other Sphinx environments are unaffected.

Nested section includes prepare their source documents before copying them into their parent source.
The callback later sees those copied descendants when preparing the parent's assembled tree, so transformations over descendants should be idempotent.
Your callback supplies presentation and validation rules.
RST path validation, dependency tracking, and circular-include checks still apply.
