|Build Status| |PyPI|

sphinx-section-include
======================

Include selected sections of reStructuredText documents in Sphinx projects.
The extension copies parsed nodes, retaining nested headings, code blocks, source locations, and references.
It also provides a typed Python API for extensions that select and transform sections themselves.

Installation
------------

.. code-block:: console

   $ pip install sphinx-section-include

Enable the extension in ``conf.py``:

.. code-block:: python

   """Enable section inclusion in this Sphinx project."""

   extensions = ["sphinx_section_include"]

Including a section
-------------------

.. code-block:: rst

   .. include-section:: manual.rst
      :section: Getting started / Configuration
      :include-heading:
      :exclude-sections: Advanced configuration

``:section:`` is required.
It accepts an exact heading, a slash-separated heading path, or an RST label prefixed by ``#``.
Literal heading matches take precedence, so headings containing slashes remain selectable.
Missing or ambiguous selections fail with a build diagnostic.

``:include-heading:`` includes the selected section's heading.
Without it, only the section's contents and nested sections are included.
``:exclude-sections:`` accepts one descendant selector per line.

Paths are relative to the including document.
A leading ``/`` selects a path relative to the Sphinx source directory.
Sources must be existing ``.rst`` files within that directory.
Self-inclusion and circular section includes are rejected.

Source documents are parsed with registered directives, substitutions, ``rst_prolog``, and ``rst_epilog``.
Dependencies from nested includes are tracked for incremental builds.
Internal anchors are namespaced so the same section can appear more than once.
Links outside the excerpt retain their source document, and local image paths retain their source directory.
Standard Sphinx reference resolution and builder URI conventions apply.

Python API
----------

``find_sections(document=..., selector=...)`` returns all matching sections.
``select_section(document=..., selector=...)`` requires exactly one match and raises ``ValueError`` otherwise.

``copy_section(section=..., include_heading=True, exclude_sections=())`` returns independent copied nodes without modifying the source tree.
Exclusions are resolved section nodes and must be descendants of the selection.
This function preserves document structure and does not apply rendering policy.

For Sphinx directive authors, ``read_document(directive=..., source=..., docname=None)`` parses an RST source and records its dependencies.
The default parsing context is the source document.
A ``docname`` override supports extensions whose embedded content uses the caller's context.
Temporary context is restored after parsing.
``resolve_source(directive=..., source=...)`` validates and resolves the path.
Both helpers require an active Sphinx build, which supplies the source directory and directive context.

This library was extracted from `sphinx-hackerrank <https://github.com/adamtheturtle/sphinx-hackerrank>`_.
HackerRank layouts, language filtering, and HTML export remain in that extension.

Development
-----------

See `CONTRIBUTING.rst <CONTRIBUTING.rst>`_ for local checks and release steps.
The sample project exercises section inclusion without HackerRank dependencies.

License
-------

MIT.
See ``LICENSE``.

.. |Build Status| image:: https://github.com/adamtheturtle/sphinx-section-include/actions/workflows/ci.yml/badge.svg?branch=main
   :target: https://github.com/adamtheturtle/sphinx-section-include/actions
.. |PyPI| image:: https://badge.fury.io/py/sphinx-section-include.svg
   :target: https://badge.fury.io/py/sphinx-section-include
