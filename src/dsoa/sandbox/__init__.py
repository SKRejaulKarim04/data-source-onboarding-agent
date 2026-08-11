"""Isolated execution of generated connectors."""

from .runner import ConnectionSandbox, SandboxResult

__all__ = ["ConnectionSandbox", "SandboxResult"]
