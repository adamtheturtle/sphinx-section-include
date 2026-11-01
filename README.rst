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

Include a section:

.. code-block:: rst

   .. include-section:: manual.rst
      :section: Getting started / Configuration
      :include-heading:
      :exclude-sections: Advanced configuration

Select by exact heading, heading path, or ``#label``.
Omit ``:include-heading:`` to include only the section's contents.
``:exclude-sections:`` accepts one descendant selector per line.
Paths are relative to the including document, or to the Sphinx source directory when prefixed with ``/``.

See the `examples <https://github.com/adamtheturtle/sphinx-section-include/tree/main/sample/source>`_ and `contributor guide <https://github.com/adamtheturtle/sphinx-section-include/blob/main/CONTRIBUTING.rst>`_.

.. |Build Status| image:: https://github.com/adamtheturtle/sphinx-section-include/actions/workflows/ci.yml/badge.svg?branch=main
   :target: https://github.com/adamtheturtle/sphinx-section-include/actions
.. |PyPI| image:: https://badge.fury.io/py/sphinx-section-include.svg
   :target: https://badge.fury.io/py/sphinx-section-include
