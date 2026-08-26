# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""``/engine`` — user-facing alias for semantic-engine switching.

Zero new selection machinery: everything forwards to the existing
``AgentConfig.set_active_semantic`` (project pin) and the agent.yml
``default: true`` flag (global), the same actions the ``/services`` TUI
exposes. ``engine`` is just the vocabulary callers actually use.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from rich.console import Console

from datus.utils.loggings import get_logger

logger = get_logger(__name__)


class EngineCommands:
    """Handlers for the ``/engine`` slash command."""

    def __init__(self, cli: Any):
        self.cli = cli

    # ── entry point ──────────────────────────────────────────────────

    def cmd_engine(self, arg_line: str) -> Optional[str]:
        """``/engine [name]`` or ``/engine --global name``."""
        args = (arg_line or "").strip().split()
        global_flag = "--global" in args or "-g" in args
        name: Optional[str] = next((a for a in args if not a.startswith("-")), None)

        if not name:
            self._show()
            return None

        available = self._available_engines()
        if name not in available:
            self._print_error(
                f"engine '{name}' is not configured in agent.services.semantic_layer. "
                f"Available: {', '.join(available)}"
            )
            return None

        if global_flag:
            self._set_global_default(name)
        else:
            self.cli.agent_config.set_active_semantic(name)
            self._print_success(f"engine → {name} (project default)")
        self._reload()
        return None

    # ── pieces ───────────────────────────────────────────────────────

    def _available_engines(self) -> List[str]:
        return list(getattr(self.cli.agent_config, "semantic_layer_configs", {}) or {})

    def _resolved(self) -> str:
        try:
            return self.cli.agent_config.resolve_semantic_adapter() or ""
        except Exception:
            return ""

    def _show(self) -> None:
        resolved = self._resolved()
        lines = ["Semantic engine (agent.services.semantic_layer):"]
        for name in self._available_engines():
            marker = " ← current" if name == resolved else ""
            lines.append(f"  {'*' if name == resolved else ' '} {name}{marker}")
        lines.append("")
        lines.append("Switch: /engine <name>   Global default: /engine --global <name>")
        self._print("\n".join(lines))

    def _set_global_default(self, name: str) -> None:
        from datus.configuration.agent_config_loader import configuration_manager

        mgr = configuration_manager()
        services = dict(mgr.get("services", {}) or {})
        section = dict(services.get("semantic_layer", {}) or {})
        for entry_name, raw in section.items():
            if not isinstance(raw, dict):
                continue
            if entry_name == name:
                raw["default"] = True
            else:
                raw.pop("default", None)
            section[entry_name] = raw
        services["semantic_layer"] = section
        mgr.update_item("services", services, save=True)
        self._print_success(f"{name} is now the global default semantic engine")

    def _reload(self) -> None:
        reload_fn = getattr(self.cli, "_reload_agent_config", None)
        if callable(reload_fn):
            reload_fn()

    # ── output helpers (thin wrappers for testability) ───────────────

    def _console(self) -> Console:
        console = getattr(self.cli, "console", None)
        return console if isinstance(console, Console) else Console()

    def _print(self, text: str) -> None:
        self._console().print(text)

    def _print_success(self, text: str) -> None:
        console = self._console()
        console.print(f"[green]✓[/green] {text}")

    def _print_error(self, text: str) -> None:
        self._console().print(f"[red]{text}[/red]")
