"""Indeed-CLI: turn Indeed job links into clean Markdown.

Standard-library only — no third-party dependencies.
"""

from .parse import Job, parse_job
from .render import render_markdown

__version__ = "0.1.0"
__all__ = ["Job", "parse_job", "render_markdown", "__version__"]
