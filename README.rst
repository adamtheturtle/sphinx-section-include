|Build Status| |PyPI|

sphinx-section-include
======================

Include selected reStructuredText sections in Sphinx documentation.

.. code-block:: console

   $ pip install sphinx-section-include

Add to ``conf.py``:

.. code-block:: python

   """Sphinx configuration."""

   extensions = ["sphinx_section_include"]

Include a section from a file relative to the current document:

.. code-block:: rst

   .. include-section:: manual.rst
      :section: Configuration
      :include-heading:

Omit ``:include-heading:`` to include only the section's contents.
Use ``:section-path:`` for nested headings or ``:section-label:`` for an RST label.
Use ``:heading-style: rubric`` for informal headings outside the document hierarchy.

See the `reference <https://github.com/adamtheturtle/sphinx-section-include/blob/main/API.rst>`_ for selection, exclusions, and the Python API, or browse the `examples <https://github.com/adamtheturtle/sphinx-section-include/tree/main/sample/source>`_.
To contribute, see the `contributor guide <https://github.com/adamtheturtle/sphinx-section-include/blob/main/CONTRIBUTING.rst>`_.

.. |Build Status| image:: https://github.com/adamtheturtle/sphinx-section-include/actions/workflows/ci.yml/badge.svg?branch=main
   :target: https://github.com/adamtheturtle/sphinx-section-include/actions
.. |PyPI| image:: https://badge.fury.io/py/sphinx-section-include.svg
   :target: https://badge.fury.io/py/sphinx-section-include
