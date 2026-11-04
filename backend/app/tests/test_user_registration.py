"""User profile fields are persisted on creation and editing."""
import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.models.profile import Profile
from app.db.models.user import User
from app.main import app


async def test_create_user_with_profile_and_details(admin_headers):
    name = f"registration-{uuid.uuid4().hex}"
    profile_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(Profile(id=profile_id, name=name))
        await db.commit()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/users", headers=admin_headers, json={
                "username": name, "password": "test-password", "full_name": "Test User", "profile_id": str(profile_id),
                "phone": "123456", "job_title": "Engineer", "department": "IT", "is_active": False,
            })
            assert response.status_code == 201, response.text
            user = response.json()
            assert user["profile_id"] == str(profile_id)
            assert (user["phone"], user["job_title"], user["department"], user["is_active"]) == ("123456", "Engineer", "IT", False)
            response = await client.patch(f"/api/v1/users/{user['id']}", headers=admin_headers, json={"department": "Support", "is_active": True})
            assert response.status_code == 200
            assert response.json()["department"] == "Support"
            assert response.json()["is_active"] is True
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.username == name))
            await db.execute(delete(Profile).where(Profile.id == profile_id))
            await db.commit()
