"""Phase 1 contract: the clean project exposes importable package boundaries."""

import importlib

import pytest


@pytest.mark.parametrize(
    "component",
    ["api", "core", "providers", "search", "storage", "analysis", "web"],
)
def test_litwatch_component_is_importable(component: str) -> None:
    package = importlib.import_module("litwatch")
    module = importlib.import_module(f"litwatch.{component}")

    assert package.__package__ == "litwatch"
    assert module.__package__ == f"litwatch.{component}"
