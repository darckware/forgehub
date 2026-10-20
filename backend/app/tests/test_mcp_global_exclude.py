"""Servidores MCP "para todos os agentes" não alcançam agentes de acesso mínimo (Maia)."""

from types import SimpleNamespace

from app.core import mcp_catalog_apply as apply
from app.core.config import settings


def test_maia_fica_fora_dos_servidores_globais(monkeypatch):
    monkeypatch.setattr(settings, "MCP_GLOBAL_EXCLUDED_SLUGS", "maia")
    assert apply.agent_excluded_from_global(SimpleNamespace(profile_slug="maia"))
    assert apply.agent_excluded_from_global(SimpleNamespace(profile_slug=" Maia "))
    assert not apply.agent_excluded_from_global(SimpleNamespace(profile_slug="athos"))
    assert not apply.agent_excluded_from_global(SimpleNamespace(profile_slug=None))


async def test_apply_global_servers_pula_agente_excluido(monkeypatch):
    monkeypatch.setattr(settings, "MCP_GLOBAL_EXCLUDED_SLUGS", "maia")
    monkeypatch.setattr(apply, "agent_is_mcp_eligible", lambda agent: True)

    class _DB:
        async def execute(self, *a, **k):  # não deve nem consultar o catálogo
            raise AssertionError("consultou o catálogo para um agente excluído")

    assert await apply.apply_global_servers_to_agent(_DB(), SimpleNamespace(profile_slug="maia")) == []
