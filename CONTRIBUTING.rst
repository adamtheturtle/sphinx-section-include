Contributing
============

Contributions to this repository must pass tests and linting.

CI is the canonical source of truth.

Install contribution dependencies
---------------------------------

Install Python dependencies in a virtual environment.

.. code-block:: shell

   uv sync --group=dev

Spell checking requires ``enchant``.
This can be installed on macOS, for example, with `Homebrew`_:

.. code-block:: shell

   brew install enchant

and on Ubuntu with ``apt``:

.. code-block:: shell

   apt-get install -y enchant

Install ``pre-commit`` hooks:

.. code-block:: shell

   uv run --group=dev prek install

Linting
-------

Run lint tools either by committing, or with:

.. code-block:: shell

   uv run --group=dev prek run --all-files --hook-stage pre-commit --verbose
   uv run --group=dev prek run --all-files --hook-stage pre-push --verbose
   uv run --group=dev prek run --all-files --hook-stage manual --verbose

.. _Homebrew: https://brew.sh

Running tests
-------------

Run ``pytest``:

.. code-block:: shell

   uv run --group=dev pytest --cov --cov-config=pyproject.toml

Continuous integration
----------------------

Tests are run on GitHub Actions.
The configuration is in ``.github/workflows/``.
CI builds the sample with serial and parallel Sphinx readers, runs tests with 100% branch coverage, and builds distributions.
It also installs the wheel and builds the sample outside the checkout.
The test matrix covers Python 3.12 through 3.15 on Ubuntu and Windows with highest and lowest direct dependencies.

Run the sample and packaging checks locally:

.. code-block:: shell

   uv run --group=dev sphinx-build -W -b html sample/source sample/build
   uv build
   uv run --group=release check-wheel-contents dist/*.whl
   uv run --group=dev python tests/wheel_smoke.py

Release Process
---------------

Outcomes
~~~~~~~~

* A new ``git`` tag available to install.
* A new package on PyPI.

Perform a Release
~~~~~~~~~~~~~~~~~

Versions come from Git tags through ``setuptools-scm``.
The release workflow tags the reviewed commit and uses PyPI trusted publishing with the ``release`` environment.
Configure the trusted publisher and set ``PYPI_PUBLISH_ENABLED`` to ``true`` before dispatching a release.

#. `Install GitHub CLI`_.

#. Prepare release notes for the next CalVer version in a pull request.
   Use the current date and increment the final numeric suffix for another release on the same date:

   .. code-block:: shell

      uv run --group=release towncrier build --yes --version 2026.10.30.2
      uv run --group=dev snapper --native --max-width 0 --in-place changelog/2026.10.30.2.md

   Commit the generated changelog and removed fragments, then merge after the required checks pass.

#. Dispatch the release from ``main``:

   .. code-block:: shell

      gh workflow run release.yml --repo adamtheturtle/sphinx-section-include

   The workflow calculates the next version and requires its changelog file to exist.
   It creates the tag and distributions without pushing a new commit to ``main``.

.. _Install GitHub CLI: https://cli.github.com/manual/installation


Release notes
-------------

Write user-facing changes as Markdown in ``newsfragments/<issue>.change.md``.
Towncrier writes one Markdown file per version, used directly for GitHub release notes.
Invalid fragment names fail release assembly.
