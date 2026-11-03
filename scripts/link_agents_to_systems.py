#!/usr/bin/env python3
"""Vincula os agentes aos sistemas correspondentes no ForgeHub.

Registra as associações em `company.project_agent_memberships` com papéis,
permissões e status ativo para que o ForgeHub tenha o controle operacional
de quais agentes têm acesso e atuação em cada sistema do ecossistema.
"""

import os
import sys
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor

# No credential in the repository: the target comes from the environment.
# It writes directly (no API, no audit); prefer the API for new registrations.
DB_URI = os.environ.get("FORGEHUB_SCRIPT_DB_URL", "")

# Mapeamento: project_name -> lista de (profile_slug, role, can_review, can_approve, allocation_percent)
MEMBERSHIPS = {
    "Darckware Platform": [
        ("porthus", "architect", True, True, 20.0),
        ("aramis", "developer", True, False, 30.0),
        ("dartan", "designer", False, False, 30.0),
        ("lara", "coordinator", False, False, 50.0),
        ("athos", "planner", True, True, 10.0),
        ("maia", "knowledge_management", False, False, 10.0),
    ],
    "ForgeHub Control Plane": [
        ("athos", "coordinator", True, True, 30.0),
        ("porthus", "architect", True, True, 20.0),
        ("aramis", "developer", True, False, 20.0),
        ("dartan", "designer", False, False, 20.0),
        ("daedalus", "planner", True, True, 20.0),
        ("hephaestus", "release_manager", True, True, 20.0),
        ("aegis", "security_reviewer", True, True, 10.0),
        ("themis", "compliance", True, True, 10.0),
        ("scriba", "documentation", False, False, 10.0),
        ("atlas", "planner", True, False, 15.0),
        ("mnemosyne", "knowledge_management", False, False, 10.0),
    ],
    "ForgeRouter Gateway": [
        ("athos", "coordinator", True, True, 20.0),
        ("porthus", "architect", True, True, 20.0),
        ("aramis", "developer", True, False, 25.0),
        ("hephaestus", "release_manager", True, True, 20.0),
        ("aegis", "security_reviewer", True, True, 15.0),
    ],
    "ForgeVault Security": [
        ("aegis", "security_reviewer", True, True, 40.0),
        ("porthus", "architect", True, True, 25.0),
        ("aramis", "developer", True, False, 25.0),
        ("athos", "coordinator", True, True, 10.0),
    ],
    "Hindsight Memory": [
        ("mnemosyne", "knowledge_management", True, True, 50.0),
        ("porthus", "architect", True, True, 15.0),
        ("aramis", "developer", True, False, 20.0),
        ("athos", "coordinator", True, True, 15.0),
    ],
    "CoreTI Platform": [
        ("maia", "coordinator", False, False, 40.0),
        ("porthus", "architect", True, True, 15.0),
        ("aramis", "developer", True, False, 25.0),
        ("dartan", "designer", False, False, 20.0),
    ],
    "Duplica Reprografia": [
        ("porthus", "architect", True, True, 20.0),
        ("aramis", "developer", True, False, 30.0),
        ("dartan", "designer", False, False, 30.0),
        ("athos", "coordinator", True, True, 10.0),
    ],
    "SAEDAS Platform": [
        ("athos", "coordinator", True, True, 30.0),
        ("porthus", "architect", True, True, 20.0),
        ("aramis", "developer", True, False, 30.0),
        ("maia", "knowledge_management", False, False, 20.0),
    ],
    "Moodle Casa da Inovação": [
        ("athos", "coordinator", True, True, 20.0),
        ("porthus", "architect", True, True, 20.0),
        ("aramis", "developer", True, False, 30.0),
        ("scriba", "documentation", False, False, 20.0),
    ],
}


def link_memberships():
    if not DB_URI:
        sys.exit("Defina FORGEHUB_SCRIPT_DB_URL (postgresql://usuario:senha@host:porta/banco).")
    conn = psycopg2.connect(DB_URI)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Busca agents por profile_slug
        cur.execute("SELECT id, name, profile_slug FROM company.agents WHERE is_active = true;")
        agents = {row["profile_slug"]: row["id"] for row in cur.fetchall()}

        # Busca projects por name
        cur.execute("SELECT id, name FROM company.projects;")
        projects = {row["name"]: row["id"] for row in cur.fetchall()}

        total_linked = 0
        print("Vinculando agentes aos sistemas no ForgeHub...")

        for project_name, member_list in MEMBERSHIPS.items():
            project_id = projects.get(project_name)
            if not project_id:
                print(f"  [AVISO] Projeto '{project_name}' não encontrado no banco. Pulando...")
                continue

            print(f"\nSistema: {project_name}")
            for slug, role, can_review, can_approve, alloc in member_list:
                agent_id = agents.get(slug)
                if not agent_id:
                    print(f"  [AVISO] Agente com slug '{slug}' não encontrado. Pulando...")
                    continue

                cur.execute(
                    """
                    SELECT id FROM company.project_agent_memberships
                    WHERE project_id = %s AND agent_id = %s;
                    """,
                    (project_id, agent_id),
                )
                m_row = cur.fetchone()
                if m_row:
                    cur.execute(
                        """
                        UPDATE company.project_agent_memberships
                        SET role = %s, can_review = %s, can_approve = %s,
                            allocation_percent = %s, status = 'active', updated_at = NOW()
                        WHERE id = %s;
                        """,
                        (role, can_review, can_approve, alloc, m_row["id"]),
                    )
                    print(f"  [OK] Vínculo atualizado: @{slug} ({role})")
                else:
                    mem_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO company.project_agent_memberships (
                            id, project_id, agent_id, role, status,
                            allocation_percent, can_review, can_approve
                        )
                        VALUES (%s, %s, %s, %s, 'active', %s, %s, %s);
                        """,
                        (mem_id, project_id, agent_id, role, alloc, can_review, can_approve),
                    )
                    print(f"  [+] Vínculo criado: @{slug} ({role})")
                total_linked += 1

        conn.commit()
        print(f"\nConcluído com sucesso! {total_linked} vínculos de agentes estabelecidos nos sistemas.")

    except Exception as e:
        conn.rollback()
        print(f"Erro ao vincular agentes: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    link_memberships()
