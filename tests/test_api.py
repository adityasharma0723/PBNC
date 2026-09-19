"""Tests for API endpoints: auth, documents, error envelope, and authorization isolation.

These tests use httpx with the ASGI transport to test the API without
starting a server. The FakeExtractor is used for all tests.
"""

import io
import uuid

import pytest
import pytest_asyncio
from PIL import Image
from httpx import AsyncClient

def _make_png_bytes(width=200, height=300) -> bytes:
    """Create a minimal valid PNG for upload tests."""
    img = Image.new("RGB", (width, height), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

@pytest.mark.asyncio
class TestAuth:

    async def test_register_success(self, client: AsyncClient, db_session):

        from app.main import app
        from app.api.deps import get_db

        async def override_db():
            yield db_session

        app.dependency_overrides[get_db] = override_db

        from app.api.deps import get_current_user
        saved = app.dependency_overrides.pop(get_current_user, None)

        from httpx import ASGITransport, AsyncClient as AC
        transport = ASGITransport(app=app)
        async with AC(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/v1/auth/register", json={
                "email": "new@example.com",
                "password": "password123",
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["email"] == "new@example.com"
            assert "id" in data

        if saved:
            app.dependency_overrides[get_current_user] = saved

    async def test_register_duplicate_email(self, client: AsyncClient, db_session):
        from app.main import app
        from app.api.deps import get_db, get_current_user

        async def override_db():
            yield db_session

        app.dependency_overrides[get_db] = override_db
        saved = app.dependency_overrides.pop(get_current_user, None)

        from httpx import ASGITransport, AsyncClient as AC
        transport = ASGITransport(app=app)
        async with AC(transport=transport, base_url="http://test") as ac:

            await ac.post("/api/v1/auth/register", json={
                "email": "dup@example.com", "password": "pass123"
            })

            resp = await ac.post("/api/v1/auth/register", json={
                "email": "dup@example.com", "password": "pass456"
            })
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "CONFLICT"

        if saved:
            app.dependency_overrides[get_current_user] = saved

@pytest.mark.asyncio
class TestDocuments:

    async def test_upload_png(self, client: AsyncClient, upload_dir):
        png = _make_png_bytes()
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("test.png", png, "image/png")},
            data={"role": "question_paper"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert "id" in data

    async def test_upload_invalid_type(self, client: AsyncClient, upload_dir):
        """Uploading a non-PDF/image should be rejected."""
        fake_exe = b"MZ" + b"\x00" * 100
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("test.pdf", fake_exe, "application/pdf")},
        )

        assert resp.status_code in (415, 422)
        assert "error" in resp.json()

    async def test_upload_empty_file(self, client: AsyncClient, upload_dir):
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert resp.status_code == 422

    async def test_list_documents(self, client: AsyncClient, upload_dir):

        png = _make_png_bytes()
        await client.post(
            "/api/v1/documents",
            files={"file": ("test.png", png, "image/png")},
        )

        resp = await client.get("/api/v1/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    async def test_get_document_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/documents/{fake_id}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_delete_document(self, client: AsyncClient, upload_dir):
        png = _make_png_bytes()
        upload_resp = await client.post(
            "/api/v1/documents",
            files={"file": ("test.png", png, "image/png")},
        )
        doc_id = upload_resp.json()["id"]

        resp = await client.delete(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 204

        resp = await client.get(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 404

@pytest.mark.asyncio
class TestErrorEnvelope:

    async def test_404_uses_error_envelope(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/documents/{uuid.uuid4()}")
        data = resp.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    async def test_422_uses_error_envelope(self, client: AsyncClient, upload_dir):
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("empty.png", b"", "image/png")},
        )
        data = resp.json()
        assert "error" in data

    async def test_request_validation_uses_error_envelope(self, client: AsyncClient):
        """Invalid JSON / schema validation error returns the standard error envelope."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-a-valid-email"},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "details" in data["error"]

@pytest.mark.asyncio
class TestAuthorizationIsolation:
    """Prove user B cannot access user A's resources."""

    async def test_user_b_cannot_see_user_a_documents(
        self, client: AsyncClient, other_client: AsyncClient, upload_dir
    ):

        png = _make_png_bytes()
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("test.png", png, "image/png")},
        )
        doc_id = resp.json()["id"]

        resp = await other_client.get(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 404

    async def test_user_b_cannot_delete_user_a_document(
        self, client: AsyncClient, other_client: AsyncClient, upload_dir
    ):
        png = _make_png_bytes()
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("test.png", png, "image/png")},
        )
        doc_id = resp.json()["id"]

        resp = await other_client.delete(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 404

    async def test_user_b_cannot_list_user_a_documents(
        self, client: AsyncClient, other_client: AsyncClient, upload_dir
    ):
        png = _make_png_bytes()
        await client.post(
            "/api/v1/documents",
            files={"file": ("test.png", png, "image/png")},
        )

        resp = await other_client.get("/api/v1/documents")
        data = resp.json()
        assert data["total"] == 0

    async def test_user_b_cannot_access_user_a_questions(
        self, client: AsyncClient, other_client: AsyncClient, upload_dir
    ):
        png = _make_png_bytes()
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("test.png", png, "image/png")},
        )
        doc_id = resp.json()["id"]

        resp = await other_client.get(f"/api/v1/documents/{doc_id}/questions")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_user_b_cannot_access_or_modify_user_a_groups(
        self, client: AsyncClient, other_client: AsyncClient
    ):

        resp = await client.post("/api/v1/groups", json={"name": "User A Private Group"})
        assert resp.status_code == 201
        group_id = resp.json()["id"]

        resp = await other_client.get(f"/api/v1/groups/{group_id}")
        assert resp.status_code == 404

        resp = await other_client.get("/api/v1/groups")
        assert resp.status_code == 200
        assert not any(g["id"] == group_id for g in resp.json())
