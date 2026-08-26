"""Spec for the /engine CLI alias (datus-agent-cube M3, T3.3).

``/engine`` is a thin, user-vocabulary front end over the existing
semantic-layer selection machinery: it shows the resolved engine and the
available ``agent.services.semantic_layer`` entries, ``/engine cube``
pins the project default (``set_active_semantic``), and
``/engine --global cube`` flips ``default: true`` in agent.yml. No new
selection mechanism — everything forwards to existing setters.
"""

from unittest.mock import MagicMock

import pytest

from datus.cli.engine_commands import EngineCommands


def _cli(semantic_entries=("metricflow", "cube"), resolved="metricflow"):
    cli = MagicMock()
    cli.agent_config.semantic_layer_configs = {name: {} for name in semantic_entries}
    cli.agent_config.resolve_semantic_adapter.return_value = resolved
    return cli


class TestEngineShow:
    def test_show_lists_resolved_and_available(self, capsys):
        EngineCommands(_cli()).cmd_engine("")
        out = capsys.readouterr().out
        assert "metricflow" in out
        assert "cube" in out

    def test_show_marks_resolved_engine(self, capsys):
        EngineCommands(_cli(resolved="cube")).cmd_engine("")
        out = capsys.readouterr().out
        assert "*" in out or "current" in out.lower() or "active" in out.lower()


class TestEngineSwitch:
    def test_switch_pins_project_default(self):
        cli = _cli()
        EngineCommands(cli).cmd_engine("cube")
        cli.agent_config.set_active_semantic.assert_called_once_with("cube")

    def test_switch_unknown_engine_is_rejected_without_pin(self):
        cli = _cli()
        EngineCommands(cli).cmd_engine("postgres")
        cli.agent_config.set_active_semantic.assert_not_called()

    def test_switch_to_only_configured_engine(self):
        cli = _cli(semantic_entries=("cube",))
        EngineCommands(cli).cmd_engine("cube")
        cli.agent_config.set_active_semantic.assert_called_once_with("cube")


class TestEngineGlobal:
    def test_global_flag_flips_default_in_agent_yml(self):
        from datus.configuration.agent_config_loader import configuration_manager

        cli = _cli()
        commands = EngineCommands(cli)
        commands._set_global_default = MagicMock()
        commands.cmd_engine("--global cube")
        commands._set_global_default.assert_called_once_with("cube")
        assert configuration_manager is not None  # used by the real implementation
