"""The core's public API: one function per command in spec/cli.md.

The CLI and the GTK app use only this module. Everything it returns is
plain data, shaped as the contract describes."""

from __future__ import annotations

from importlib.metadata import version as package_version
from typing import Literal, TypedDict

CONTRACT = 1
"""The version of spec/cli.md this core implements."""


class Version(TypedDict):
    contract: int
    implementation: Literal["python"]
    version: str


def version() -> Version:
    return {"contract": CONTRACT, "implementation": "python", "version": package_version("silentdesk")}
