"""sandbox/executor.py extended tests — constants, error classes, init.
Coverage sprint 4-1: 66% → >=75%.
"""
from __future__ import annotations

import pytest

from orbit.sandbox.executor import (
    DEFAULT_IMAGE,
    DEFAULT_TIMEOUT,
    MAX_READONLY_MOUNTS,
    Sandbox,
    SandboxError,
    SandboxExecutionError,
    SandboxTimeoutError,
)


class TestConstants:
    def test_default_image(self):
        assert "python" in DEFAULT_IMAGE

    def test_default_timeout(self):
        assert DEFAULT_TIMEOUT > 0

    def test_max_readonly_mounts(self):
        assert MAX_READONLY_MOUNTS == 5


class TestErrorClasses:
    def test_sandbox_error_is_exception(self):
        assert isinstance(SandboxError("test"), Exception)

    def test_timeout_error_hierarchy(self):
        assert isinstance(SandboxTimeoutError("timeout"), SandboxError)

    def test_execution_error_hierarchy(self):
        assert isinstance(SandboxExecutionError("exit 1"), SandboxError)


class TestSandboxInit:
    def test_default_init(self):
        s = Sandbox()
        assert s.image == DEFAULT_IMAGE
        assert s.timeout == DEFAULT_TIMEOUT

    def test_custom_image_and_timeout(self):
        s = Sandbox(image="python:3.11-alpine", timeout=60)
        assert s.image == "python:3.11-alpine"
        assert s.timeout == 60
