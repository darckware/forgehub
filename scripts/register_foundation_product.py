#!/usr/bin/env python3
"""Register the internal Foundation product through the ForgeHub API."""
import argparse
import json
import os
import sys

import httpx

PRODUCT = "Ecossistema Foundation"
VERSION = "2026.11"
PROJECT = "Plano integrado"
DESCRIPTION = ("Foundation, agentes Hermes e infraestrutura comum do ecossistema; "
               "casa da missão e do plano integrado. Dono: Marcelo.")
PROJECT_DESCRIPTION = "Projeto comum do Plano Integrado do ecossistema (docs/plano-integrado)"


def one(items, field, value):
    matches = [item for item in items if item[field] == value]
    if len(matches) > 1:
        raise ValueError(f"Nome duplicado: {value}")
    return matches[0] if matches else None


def register(client, dry_run=False):
    def request(method, path, **kwargs):
        response = client.request(method, "/api/v1" + path, **kwargs)
        response.raise_for_status()
        return response.json()

    product = one(request("GET", "/products"), "name", PRODUCT)
    project = one(request("GET", "/projects"), "name", PROJECT)
    version = None
    if product:
        if product.get("darckware_client_id") or product.get("description") != DESCRIPTION:
            raise ValueError("Produto existente incompatível; confira descrição e cliente")
        version = one(request("GET", f"/products/{product['id']}/versions"), "version", VERSION)
        if version and version["status"] != "planned":
            raise ValueError("Versão existente não está planned")
    if project and (not version or project["product_version_id"] != version["id"]
                    or project.get("owner") != "Marcelo" or project.get("darckware_client_id")
                    or project.get("description") != PROJECT_DESCRIPTION):
        raise ValueError("Projeto existente incompatível; confira vínculo, dono, descrição e cliente")

    actions = {"product": "reused" if product else "created",
               "version": "reused" if version else "created",
               "project": "reused" if project else "created"}
    if not product and not dry_run:
        product = request("POST", "/products", json={"name": PRODUCT, "description": DESCRIPTION,
                          "initial_version": {"version": VERSION, "status": "planned"}})
        version = one(product["versions"], "version", VERSION)
        if not version:
            raise ValueError("API não retornou a versão inicial")
    elif product and not version and not dry_run:
        version = request("POST", f"/products/{product['id']}/versions",
                          json={"version": VERSION, "status": "planned"})
    if not project and not dry_run:
        project = request("POST", "/projects", json={"name": PROJECT,
                          "description": PROJECT_DESCRIPTION, "owner": "Marcelo",
                          "product_version_id": version["id"]})
    result = {f"{name}_id": obj["id"] if obj else None for name, obj in
              (("product", product), ("version", version), ("project", project))}
    result.update(actions)
    result["dry_run"] = dry_run
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-env", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        parser.error("variável de token ausente ou vazia")
    try:
        with httpx.Client(base_url=args.base_url.rstrip("/"), headers={"Authorization": f"Bearer {token}"},
                          timeout=30) as client:
            print(json.dumps(register(client, args.dry_run), ensure_ascii=False))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
