from __future__ import annotations

import sys

from sora_imagegen_tool import cli


def test_cli_prints_custom_greeting(capsys, monkeypatch):
    """CLI should print a personalized greeting when --name is supplied."""
    name = "Atlas"
    monkeypatch.setattr(sys, "argv", ["sora_imagegen_tool", "--name", name])
    cli.main()
    captured = capsys.readouterr()
    assert captured.out.strip() == f"Hello, {name}!"
