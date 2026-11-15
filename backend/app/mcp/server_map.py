"""Which ForgeHub MCP server owns each tool (MCP split plan, Fase 1; docs/architecture/MCP_SPLIT_PLAN.md).

One definition per tool stays where it is (host-bridge/forgehub_messages_mcp.py, factory_server.py,
the personal modules); this map only says which server exposes it. `serve.py <server>` builds
that server from the combined catalog, so the code is never copied.

Rules, enforced by tests/test_mcp_server_map.py:
- every tool of the combined catalog belongs to exactly one server;
- the map names no tool the catalog doesn't have (a rename must update the map);
- `forgehub_all` is the transition server (plan D3): the whole combined catalog, exactly what
  `factory_server.py` serves today. It goes away after the last migration wave + 7 days.

Server names are also the MCP entry names in each agent's config, so a tool reaches an agent as
`mcp__<server>__<tool>`. The core server keeps the name `forgehub`, so Messages tools keep their
current names.
"""
from __future__ import annotations

CORE = "forgehub"
FACTORY = "forgehub_factory"
MISSIONS = "forgehub_missions"
OPS = "forgehub_ops"
REGISTRY = "forgehub_registry"
REMOTE = "forgehub_remote"
PERSONAL = "forgehub_personal"
ALL = "forgehub_all"

SERVER_TOOLS: dict[str, frozenset[str]] = {
    # Talk, hand off and ask: every registered agent (plan D4 base set).
    CORE: frozenset({
        "send_agent_message", "list_agent_messages", "get_agent_message", "check_agent_inbox",
        "update_agent_message", "archive_agent_message",
        "list_my_incubation", "receive_incubation", "drop_incubation",
        "ask_marcelo", "list_my_questions", "record_marcelo_answer", "request_marcelo_approval",
        "propose_improvement", "propose_skill_change",
        "list_channel_members", "propose_channel_task",
        "list_agents", "get_agent_profile", "list_agent_skills",
        "get_task_context", "set_agent_unavailable",
    }),
    # Product -> project -> planning -> task, and the task execution flow.
    FACTORY: frozenset({
        "list_projects", "get_project_context", "list_project_screens", "get_project_erd",
        "list_planning_items", "list_project_tasks", "update_task_status", "report_governance_blocker",
        "create_conception_idea", "save_concept_document", "authorize_project_delivery",
        "ensure_project_scope", "add_project_screen", "save_screen_prototype_html",
        "derive_database_model", "create_database_table", "create_planning_item", "create_project_task",
        "release_planning_for_execution", "create_product_version", "close_version_and_publish",
        "add_task_dependency", "assign_task", "dispatch_task", "report_task_execution",
        "request_task_review", "return_task_for_correction", "list_my_tasks",
        # Registered only with FORGEHUB_TASK_BROWSER_ENABLED=1.
        "get_workspace_browser_capabilities", "task_browser",
    }),
    MISSIONS: frozenset({
        "create_internal_project", "manage_project_members", "attach_project_document",
        "submit_project_plan", "withdraw_project_plan", "request_mission_acceptance",
        "get_mission_criteria", "create_mission_criterion", "decide_mission_criterion",
        "get_my_mission_role", "complete_mission_product_registration",
        "list_mission_phases", "create_mission_phase", "update_mission_phase", "reorder_mission_phases",
        "sequence_planning_tasks", "request_phase_homologation", "report_phase_homologation",
        "get_mission_cycle", "mission_decide", "defer_mission_proposal", "pause_mission",
        # Registered only with FORGEHUB_MISSION_LEARNING_ENABLED=1.
        "propose_verified_learning",
    }),
    # Running the ecosystem: status, Auditor, deploy, database, Operação 24x7 routines.
    OPS: frozenset({
        "get_system_status", "list_system_backups", "run_system_backup",
        "list_audit_checks", "run_audit_checks",
        "list_deploy_containers", "restart_deploy_container", "get_container_logs",
        "list_managed_servers", "execute_database_query",
        "list_routines", "create_routine", "update_routine", "delete_routine", "run_routine_now",
        "list_routine_runs",
    }),
    # Who the agents are: profiles, skills, credentials, agent tools.
    REGISTRY: frozenset({
        "update_agent_profile", "get_agent_profile_file", "update_agent_profile_file",
        "list_skills", "grant_agent_skill", "revoke_agent_skill",
        "issue_agent_credential", "list_agent_credentials", "revoke_agent_credential",
        "list_agent_tools", "register_agent_tool", "update_agent_tool", "scan_agent_tools",
        "sync_hermes_agents",
    }),
    # Client machines, through ForgeHub only (docs/architecture/REMOTE_ACCESS_RULE.md).
    REMOTE: frozenset({
        "list_maintenance_machines", "list_maintenance_scripts", "run_maintenance_script",
        "run_remote_command", "upload_remote_file", "download_remote_file", "get_maintenance_execution",
        "propose_maintenance_script", "get_maintenance_proposal", "run_approved_maintenance_proposal",
    }),
}

# Marcelo's personal tools: whatever personal_contacts.register() adds (it registers its sibling
# modules too, and only for the agents it allows -- the Maia). Listed by prefix rather than by name
# because that module owns its catalog.
PERSONAL_PREFIXES = ("personal_", "agenda_", "tasks_", "notes_")

SERVERS = (CORE, FACTORY, MISSIONS, OPS, REGISTRY, REMOTE, PERSONAL, ALL)


def server_of(tool: str) -> str | None:
    """The server that owns a tool of the combined catalog, or None when no server does."""
    owners = [name for name, tools in SERVER_TOOLS.items() if tool in tools]
    if tool.startswith(PERSONAL_PREFIXES):
        owners.append(PERSONAL)
    return owners[0] if len(owners) == 1 else None
