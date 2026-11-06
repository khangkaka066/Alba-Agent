"""A small script must not be handed to a seven-department studio.

"Build todo.py, a tiny command-line todo app ..." contains "build" and "app", which is all the studio detector asks for,
so auto mode attached the Software Factory (11 nodes, seven departments) to a 60-line program. That run kept both
worker threads busy for over ten minutes and produced no file. The light path (one coder and reviewer with a repair step)
is what such a request needs."""

from __future__ import annotations

import asyncio

import pytest

from architect.adaptive import is_small_script_request
from architect.team_generator import MetaArchitectService
from flows.compiler import FlowCompiler
from test_adaptive_levels import _context, _generator

TODO = ("Build todo.py, a tiny command-line todo app with add, list and done commands that keeps its tasks in tasks.json. "
        "Also write test_todo.py with three tests and run them until they pass. Keep todo.py under 60 lines.")


@pytest.mark.parametrize("prompt", [
    TODO,
    "Create a small Python script that renames files in a folder",
    "Make a simple CLI app in main.py that converts CSV to JSON",
    "Write a one-file calculator app in calc.py with tests",
])
def test_small_scripts_are_recognised(prompt: str) -> None:
    assert is_small_script_request(prompt)


@pytest.mark.parametrize("prompt", [
    "Build a web app with a feature flag service",
    "Build a SaaS platform for invoicing with user accounts",
    "Create a dashboard app with a backend API and a React frontend",
    "Build an app",
    "Develop a mobile app in main.py and deploy it",
])
def test_real_products_are_not_taken_for_scripts(prompt: str) -> None:
    assert not is_small_script_request(prompt)


def test_auto_gives_the_todo_script_the_light_path() -> None:
    seen: list[str] = []
    service = MetaArchitectService(_generator(seen), FlowCompiler.validate)
    spec, summary = asyncio.run(service.generate_workflow(TODO, _context(), rigor="auto"))
    assert seen == [] and summary["level"] == "solo"
    assert [node.kind for node in spec.nodes] == ["start", "sandbox", "router", "sandbox"]


def test_auto_still_gives_a_real_software_product_the_studio() -> None:
    seen: list[str] = []
    service = MetaArchitectService(_generator(seen), FlowCompiler.validate)
    _, summary = asyncio.run(service.generate_workflow("Build a SaaS platform for invoicing with a backend and a dashboard", _context(), rigor="auto"))
    assert seen == ["_StudioDraft"] and summary["rigor"] == "full_studio"
