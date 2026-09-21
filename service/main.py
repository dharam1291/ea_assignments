"""
Entry point — kept deliberately thin.

All wiring lives in service.core.factory so that tests and alternative
entry points (CLI, Lambda handler, etc.) import create_app directly.
"""

from service.core.factory import create_app

app = create_app()
