# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

import datetime
import os
import sys

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown:

#sys.path.insert(0, os.path.abspath('../../'))
#sys.path.insert(0, os.path.abspath('../'))
#sys.path.insert(0, os.path.abspath('./'))
#sys.path.insert(0, os.path.abspath('.'))

# -- Project information -----------------------------------------------------

project = 'Ubuntu Install Guide'
copyright = f'Canonical Group Ltd, {datetime.date.today().year}'

# -- General configuration ---------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
needs_sphinx = '5.1.1'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.

extensions = [
    'm2r2',
    'sphinx_copybutton',
    'sphinx_design',
]


# Add any paths that contain templates here, relative to this directory.

templates_path = ['_templates']

# The suffix of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.

# version = version.version_string()
# release = version

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.

exclude_patterns = [
    ".sphinx/venv/*",
]

# Sphinx-copybutton config options:
# 1) prompt to be stripped from copied code.
# 2) Set to copy all lines (not just prompt lines) to ensure multiline snippets
# can be copied even if they don't contain an EOF line.
copybutton_prompt_text = '$ '
copybutton_only_copy_prompt_lines = False

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes:
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_logo = '_static/ubuntu_logo.png'
html_theme_options = {
    'light_css_variables': {
        'color-sidebar-background-border': 'none',
        'font-stack': 'Ubuntu, -apple-system, Segoe UI, Roboto, Oxygen, Cantarell, Fira Sans, Droid Sans, Helvetica Neue, sans-serif',
        'font-stack--monospace': 'Ubuntu Mono variable, Ubuntu Mono, Consolas, Monaco, Courier, monospace',
        'color-foreground-primary': '#111',
        'color-foreground-secondary': 'var(--color-foreground-primary)',
        'color-foreground-muted': '#333',
        'color-background-secondary': '#FFF',
        'color-background-hover': '#f2f2f2',
        'color-brand-primary': '#111',
        'color-brand-content': '#06C',
        'color-inline-code-background': 'rgba(0,0,0,.03)',
        'color-sidebar-link-text': '#111',
        'color-sidebar-item-background--current': '#ebebeb',
        'color-sidebar-item-background--hover': '#f2f2f2',
        'sidebar-item-line-height': '1.3rem',
        'color-link-underline': 'var(--color-background-primary)',
        'color-link-underline--hover': 'var(--color-background-primary)',
    },
    'dark_css_variables': {
        'color-foreground-secondary': 'var(--color-foreground-primary)',
        'color-foreground-muted': '#CDCDCD',
        'color-background-secondary': 'var(--color-background-primary)',
        'color-background-hover': '#666',
        'color-brand-primary': '#fff',
        'color-brand-content': '#06C',
        'color-sidebar-link-text': '#f7f7f7',
        'color-sidebar-item-background--current': '#666',
        'color-sidebar-item-background--hover': '#333',
    },
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named 'default.css' will overwrite the builtin 'default.css'.
html_static_path = ['_static']

# If you ever want to use the feedback button, turn on GH issues and then
# uncomment the github_issue_links files

html_css_files = [
    'css/logo.css',
#    'css/github_issue_links.css',
    'css/custom.css',
]
html_js_files = [
#    'js/github_issue_links.js',
]
