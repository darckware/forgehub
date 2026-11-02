#!/usr/bin/env python3
"""Cadastra todos os sistemas e produtos do ecossistema no ForgeHub.

Garante que os sistemas oficiais estejam registrados em `company.products`,
`company.product_versions` e `company.projects`, com seus caminhos de diretório
reais, URLs operacionais e tipos de solução.
"""

import sys
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor

DB_URI = "postgresql://foundation:foundation_local_dev_password@127.0.0.1:5433/forgehub"

SYSTEMS = [
    {
        "name": "Darckware",
        "description": "Empresa e sistema central: portal do cliente, site institucional, CRM, chamados, demandas e franquias de suporte/desenvolvimento.",
        "application_url": "https://darckware.net",
        "application_url_dev": "http://127.0.0.1:3000",
        "working_directory_path": "/root/project/darckware",
        "solution_type": "web_app",
        "project_name": "Darckware Platform",
        "owner": "marcelo",
    },
    {
        "name": "ForgeHub",
        "description": "Console de controle operacional e plano de comando do ecossistema: Software Factory, mensagens entre agentes, auditoria e governança.",
        "application_url": "http://127.0.0.1:4173",
        "application_url_dev": "http://127.0.0.1:8000",
        "working_directory_path": "/root/project/forgehub",
        "solution_type": "web_app",
        "project_name": "ForgeHub Control Plane",
        "owner": "athos",
    },
    {
        "name": "ForgeRouter",
        "description": "Gateway unificado de IA do ecossistema: roteamento de modelos/provedores, failover, controle de cota, telemetria e custos.",
        "application_url": "http://127.0.0.1:2100",
        "application_url_dev": "http://127.0.0.1:2100/v1",
        "working_directory_path": "/root/project/forgerouter",
        "solution_type": "api_service",
        "project_name": "ForgeRouter Gateway",
        "owner": "athos",
    },
    {
        "name": "ForgeVault",
        "description": "Cofre central de credenciais, segredos criptografados, ServiceAccounts e registro de servidores MCP com RBAC e trilha de auditoria.",
        "application_url": "http://127.0.0.1:8080",
        "application_url_dev": "http://127.0.0.1:4200",
        "working_directory_path": "/root/project/forgevault",
        "solution_type": "api_service",
        "project_name": "ForgeVault Security",
        "owner": "aegis",
    },
    {
        "name": "Hindsight",
        "description": "Memória semântica coletiva do ecossistema: retenção e recordação contínua de fatos, decisões e aprendizados entre agentes.",
        "application_url": "http://127.0.0.1:8888",
        "application_url_dev": "http://127.0.0.1:9999",
        "working_directory_path": "/root/project/hindsight",
        "solution_type": "api_service",
        "project_name": "Hindsight Memory",
        "owner": "mnemosyne",
    },
    {
        "name": "CoreTI",
        "description": "Plataforma integrada de gestão de TI: unidades escolares, setores, estagiários, ativos, chamados e diretores.",
        "application_url": "http://127.0.0.1:3100",
        "application_url_dev": "http://127.0.0.1:8095",
        "working_directory_path": "/root/project/coreti",
        "solution_type": "web_app",
        "project_name": "CoreTI Platform",
        "owner": "maia",
    },
    {
        "name": "Duplica",
        "description": "Sistema de gestão de reprografia e controle de solicitações de cópias/impressões para escolas e unidades.",
        "application_url": "http://127.0.0.1:8010",
        "application_url_dev": "http://127.0.0.1:5435",
        "working_directory_path": "/root/project/duplica",
        "solution_type": "web_app",
        "project_name": "Duplica Reprografia",
        "owner": "marcelo",
    },
    {
        "name": "SAEDAS — Saúde nas Escolas",
        "description": "Sistema de Avaliação e Gestão de Saúde nas Escolas: Dashboard analítico para gestão e aplicativo de triagem clínica em campo.",
        "application_url": "http://127.0.0.1:3200",
        "application_url_dev": "http://127.0.0.1:8096",
        "working_directory_path": "/root/project/saedas",
        "solution_type": "web_app",
        "project_name": "SAEDAS Platform",
        "owner": "athos",
    },
    {
        "name": "Moodle Casa da Inovação",
        "description": "Ambiente virtual de aprendizagem, capacitação tecnológica e cursos da Casa da Inovação.",
        "application_url": "https://moodle.casadainovacao.com",
        "application_url_dev": "http://127.0.0.1:8088",
        "working_directory_path": "/root/project/moodle",
        "solution_type": "web_app",
        "project_name": "Moodle Casa da Inovação",
        "owner": "marcelo",
    },
]


def register_systems():
    conn = psycopg2.connect(DB_URI)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        print("Registrando sistemas do ecossistema no ForgeHub...")
        for sys_info in SYSTEMS:
            # 1. Product
            cur.execute(
                "SELECT id FROM company.products WHERE name = %s;", (sys_info["name"],)
            )
            row = cur.fetchone()
            if row:
                product_id = row["id"]
                cur.execute(
                    """
                    UPDATE company.products
                    SET description = %s, application_url = %s, application_url_dev = %s, status = 'active', updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (
                        sys_info["description"],
                        sys_info["application_url"],
                        sys_info["application_url_dev"],
                        product_id,
                    ),
                )
                print(f"  [OK] Produto atualizado: {sys_info['name']} ({product_id})")
            else:
                product_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO company.products (id, name, description, status, application_url, application_url_dev)
                    VALUES (%s, %s, %s, 'active', %s, %s);
                    """,
                    (
                        product_id,
                        sys_info["name"],
                        sys_info["description"],
                        sys_info["application_url"],
                        sys_info["application_url_dev"],
                    ),
                )
                print(f"  [+] Produto criado: {sys_info['name']} ({product_id})")

            # 2. Product Version (v1.0.0)
            cur.execute(
                "SELECT id FROM company.product_versions WHERE product_id = %s AND version = '1.0.0';",
                (product_id,),
            )
            v_row = cur.fetchone()
            if v_row:
                version_id = v_row["id"]
            else:
                version_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO company.product_versions (id, product_id, version, status, release_notes)
                    VALUES (%s, %s, '1.0.0', 'published', 'Versão em produção contínua no ecossistema.');
                    """,
                    (version_id, product_id),
                )
                print(f"    [+] Versão 1.0.0 criada ({version_id})")

            # 3. Project
            cur.execute(
                "SELECT id FROM company.projects WHERE name = %s OR product_version_id = %s;",
                (sys_info["project_name"], version_id),
            )
            p_row = cur.fetchone()
            if p_row:
                project_id = p_row["id"]
                cur.execute(
                    """
                    UPDATE company.projects
                    SET description = %s, working_directory_path = %s, solution_type = %s,
                        status = 'active', owner = %s, updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (
                        sys_info["description"],
                        sys_info["working_directory_path"],
                        sys_info["solution_type"],
                        sys_info["owner"],
                        project_id,
                    ),
                )
                print(f"    [OK] Projeto atualizado: {sys_info['project_name']} ({project_id})")
            else:
                project_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO company.projects (
                        id, name, description, product_version_id, owner, status,
                        working_directory_path, solution_type, project_type, backup_enabled
                    )
                    VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, 'maintenance', true);
                    """,
                    (
                        project_id,
                        sys_info["project_name"],
                        sys_info["description"],
                        version_id,
                        sys_info["owner"],
                        sys_info["working_directory_path"],
                        sys_info["solution_type"],
                    ),
                )
                print(f"    [+] Projeto criado: {sys_info['project_name']} ({project_id})")

        conn.commit()
        print("\nTodos os 9 sistemas do ecossistema foram cadastrados com sucesso no ForgeHub!")

    except Exception as e:
        conn.rollback()
        print(f"Erro ao registrar sistemas: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    register_systems()
