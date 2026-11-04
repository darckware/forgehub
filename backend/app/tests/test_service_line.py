"""Catalog authorization and project compatibility."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.service_line import ServiceLine
from app.db.models.user import User
from app.core.security import create_access_token, hash_password
from app.main import app


@pytest.mark.asyncio
async def test_catalog_and_project_defaults(admin_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as client:
        response = await client.get("/api/v1/service-lines")
        assert response.status_code == 200
        lines = {line["slug"]: line for line in response.json()}
        assert {"software", "sustentacao", "manutencao", "suporte", "infraestrutura", "documentacao", "marketing", "missoes", "incidentes"} <= lines.keys()
        product = await client.post("/api/v1/products", json={"name": f"Service line {uuid.uuid4()}"})
        assert product.status_code == 201, product.text
        product_id = uuid.UUID(product.json()["id"])
        project_id = None
        service_project_id = None
        try:
            response = await client.post("/api/v1/projects", json={
                "name": "Default line", "product_version_id": product.json()["versions"][0]["id"],
            })
            assert response.status_code == 201, response.text
            project_id = uuid.UUID(response.json()["id"])
            assert response.json()["service_line_id"] == lines["software"]["id"]
            assert response.json()["service_line_name"] == lines["software"]["name"]
            updated = await client.patch(f"/api/v1/projects/{project_id}", json={"service_line_id": lines["sustentacao"]["id"]})
            assert updated.status_code == 200, updated.text
            assert updated.json()["service_line_name"] == lines["sustentacao"]["name"]
            updated = await client.patch(f"/api/v1/projects/{project_id}", json={"service_line_id": lines["software"]["id"]})
            assert updated.status_code == 200, updated.text
            service_response = await client.post("/api/v1/projects", json={
                "name": "Service line project", "product_version_id": product.json()["versions"][0]["id"],
                "service_line_id": lines["suporte"]["id"],
            })
            assert service_response.status_code == 201, service_response.text
            service_project_id = uuid.UUID(service_response.json()["id"])
            cockpit = (await client.get("/api/v1/factory/cockpit")).json()
            row = next(row for row in cockpit["products"] if row["product_id"] == str(product_id))
            by_id = {project["project_id"]: project for project in row["projects"]}
            assert by_id[str(project_id)]["phases"]
            assert by_id[str(service_project_id)]["phases"] == []
            assert by_id[str(service_project_id)]["service_line_name"] == lines["suporte"]["name"]
            assert (await client.delete(f'/api/v1/service-lines/{lines["software"]["id"]}')).status_code == 409
        finally:
            async with AsyncSessionLocal() as db:
                for item_id in (project_id, service_project_id):
                    if item_id:
                        await db.execute(delete(Project).where(Project.id == item_id))
                await db.execute(delete(ProductVersion).where(ProductVersion.product_id == product_id))
                await db.execute(delete(Product).where(Product.id == product_id))
                await db.commit()
        username = f"service-line-user-{uuid.uuid4().hex}"
        async with AsyncSessionLocal() as db:
            db.add(User(username=username, hashed_password=hash_password("unused"), is_admin=False))
            await db.commit()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={
                "Authorization": f"Bearer {create_access_token(username)}"
            }) as user:
                assert (await user.get("/api/v1/service-lines")).status_code == 200
                response = await user.post("/api/v1/service-lines", json={"slug": "denied", "name": "Denied"})
                assert response.status_code == 403
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(User).where(User.username == username))
                await db.execute(delete(ServiceLine).where(ServiceLine.slug == "denied"))
                await db.commit()


@pytest.mark.asyncio
async def test_legacy_project_type_defaults_and_sellable_client_link():
    from fastapi import HTTPException
    from app.api.routes.client_ops import _link_product
    from app.db.models.service_line import ServiceLine
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        product = Product(name=f"Defaults {uuid.uuid4()}", sellable=True)
        version = ProductVersion(product=product, version="0.1.0")
        db.add_all([product, version])
        await db.flush()
        projects = [Project(name=f"Default {kind}", product_version_id=version.id, project_type=kind)
                    for kind in ("creation", "maintenance", "mission")]
        db.add_all(projects)
        try:
            await db.flush()
            slugs = [await db.scalar(select(ServiceLine.slug).where(ServiceLine.id == p.service_line_id))
                     for p in projects]
            assert slugs == ["software", "sustentacao", "missoes"]
            with pytest.raises(HTTPException) as exc:
                await _link_product(db, product, uuid.uuid4(), "Client")
            assert exc.value.status_code == 422
        finally:
            await db.rollback()
