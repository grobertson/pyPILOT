"""Sphinx configuration for the pyPILOT documentation."""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath("../src"))
sys.path.insert(0, os.path.abspath("_ext"))

# -- Project information -----------------------------------------------------

project = "pyPILOT"
author = "F. G. Robertson"
copyright = f"{date.today().year}, F. G. Robertson"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

templates_path: list[str] = []
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------

html_theme = "alabaster"
html_static_path: list[str] = []

# -- Extension configuration -------------------------------------------------

autodoc_typehints = "description"
autodoc_member_order = "bysource"

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

# `Path` and friends are referenced from type annotations throughout the API
# docs. Sphinx resolves those through the Python inventory when it is
# reachable, but a doc build with no network must not fail over them, so the
# handful of stdlib classes that appear are declared here. Silencing the whole
# reference domain would defeat the point of `nitpicky`.
nitpick_ignore = [
    ("py:class", "Path"),
]

nitpicky = True

# -- PILOT syntax highlighting ------------------------------------------------

from pilot_lexer import PilotLexer


def setup(app):  # type: ignore[no-untyped-def]
    """Register the PILOT Pygments lexer with Sphinx."""
    app.add_lexer("pilot", PilotLexer)
