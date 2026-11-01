Extension API
=============

``read_document`` parses an RST source using the active Sphinx environment and records its include dependencies.
``find_sections`` and ``select_section`` select headings, heading paths, or labels.
``copy_section`` copies a selection without changing its source tree.

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
