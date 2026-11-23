import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from api.auth import ISSUER
from api.bootstrap import create_app
from core.config import Settings

SOURCE = "\n".join(
    f"Architecture lesson number {number} describes a distinct design decision."
    for number in range(1, 10)
)
PASSWORD = "examify-demo-password"
SECRET = "test-signing-key-for-local-api-verification-only"


@pytest.fixture
def client(tmp_path):
    app = create_app(
        Settings(jwt_secret=SECRET, max_pdf_size_bytes=2048), database_path=tmp_path / "demo.db"
    )
    with TestClient(app) as test_client:
        yield test_client


def account(client, email):
    body = {"email": email, "password": PASSWORD}
    response = client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 201, response.text
    assert "password_hash" not in response.json()
    response = client.post("/api/v1/auth/login", json=body)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def owner(client):
    return account(client, "owner@example.com")


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]


def add_document(client, headers):
    response = client.post(
        "/api/v1/documents/from-text", headers=headers, json={"title": "Lecture", "text": SOURCE}
    )
    assert response.status_code == 201, response.text
    return "/api/v1/documents/" + response.json()["document_id"]


def generate(client, headers, path, **options):
    response = client.post(path + "/generate-questions", headers=headers, json=options)
    assert response.status_code == 200, response.text
    return response.json()


def approve(client, headers, questions):
    for question in questions:
        response = client.post(
            f"/api/v1/questions/{question['question_id']}/review",
            headers=headers,
            json={"status": "approved"},
        )
        assert response.status_code == 200, response.text


def new_exam(client, headers, document, count=5, mode="practice"):
    result = client.post(
        "/api/v1/exams",
        headers=headers,
        json={
            "document_id": document.rsplit("/", 1)[-1],
            "target_question_count": count,
            "mode": mode,
        },
    )
    assert result.status_code == 201, result.text
    return "/api/v1/exams/" + result.json()["session_id"]


def test_health_static_and_auth(client, owner):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    assert 'dir="rtl"' in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    response = client.get("/api/v1/documents")
    assert_error(response, 401, "AUTHENTICATION_FAILED")
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert client.get("/api/v1/documents", headers=owner).json() == []
    assert_error(
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "  OWNER@example.com ",
                "password": PASSWORD,
            },
        ),
        409,
        "STATE_CONFLICT",
    )
    assert_error(
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.com",
                "password": "incorrect-password",
            },
        ),
        401,
        "AUTHENTICATION_FAILED",
    )
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "iss": ISSUER,
            "sub": str(uuid4()),
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        SECRET,
        algorithm="HS256",
    )
    assert_error(
        client.get("/api/v1/documents", headers={"Authorization": f"Bearer {expired}"}),
        401,
        "AUTHENTICATION_FAILED",
    )


def test_documents_and_sharing(client, owner):
    path = add_document(client, owner)
    recipient = account(client, "recipient@example.com")
    assert_error(client.get(path, headers=recipient), 404, "RESOURCE_NOT_FOUND")
    assert client.get("/api/v1/documents", headers=recipient).json() == []
    assert (
        client.post(
            path + "/share", headers=owner, json={"email": "recipient@example.com"}
        ).status_code
        == 200
    )
    assert client.get(path, headers=recipient).json()["is_owner"] is False
    assert len(client.get("/api/v1/documents", headers=recipient).json()) == 1
    assert_error(
        client.post(path + "/generate-questions", headers=recipient), 403, "PERMISSION_DENIED"
    )
    questions = generate(client, owner, path, question_count=5)["questions"]
    assert client.get(path + "/questions", headers=recipient).json() == []
    assert_error(
        client.post(
            f"/api/v1/questions/{questions[0]['question_id']}/review",
            headers=recipient,
            json={"status": "approved"},
        ),
        403,
        "PERMISSION_DENIED",
    )
    approve(client, owner, questions)
    for question in client.get(path + "/questions", headers=recipient).json():
        assert {"correct_index", "explanation", "sources"}.isdisjoint(question)


def test_upload_txt_pdf_and_errors(client, owner):
    url = "/api/v1/documents/upload"
    response = client.post(url, headers=owner, files={"file": ("notes.txt", SOURCE.encode())})
    assert response.status_code == 201
    assert response.json()["page_count"] == 1
    assert_error(
        client.post(url, headers=owner, files={"file": ("notes.csv", b"a,b")}),
        415,
        "UNSUPPORTED_FILE_TYPE",
    )
    assert_error(
        client.post(url, headers=owner, files={"file": ("large.txt", b"x" * 2049)}),
        413,
        "UPLOAD_TOO_LARGE",
    )
    assert_error(
        client.post(url, headers=owner, files={"file": ("invalid.pdf", b"broken")}),
        422,
        "VALIDATION_FAILED",
    )
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    page = writer.add_blank_page(width=200, height=200)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    ),
                }
            ),
        }
    )
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 20 140 Td (A modular monolith deploys as a single unit.) Tj ET")
    page[NameObject("/Contents")] = content
    pdf = BytesIO()
    writer.write(pdf)
    uploaded = client.post(url, headers=owner, files={"file": ("lecture.pdf", pdf.getvalue())})
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert (document["page_count"], document["extracted_page_count"]) == (2, 1)
    result = generate(
        client, owner, f"/api/v1/documents/{document['document_id']}", question_count=1
    )
    assert result["questions"][0]["sources"][0]["page_number"] == 2


def test_exam_adapts_retries_and_reports(client, owner):
    document = add_document(client, owner)
    questions = generate(client, owner, document, question_count=8, language="fa")["questions"]
    assert len(questions) == 8
    assert generate(client, owner, document, question_count=8)["questions"] == []
    keys = {item["question_id"]: item["correct_index"] for item in questions}
    exam = new_exam(client, owner, document, mode="graded")
    assert_error(client.get(exam + "/next-question", headers=owner), 409, "INVALID_EXAM_TRANSITION")
    assert_error(client.post(exam + "/start", headers=owner), 409, "STATE_CONFLICT")
    approve(client, owner, questions)
    assert client.post(exam + "/start", headers=owner).status_code == 200
    first = client.get(exam + "/next-question", headers=owner)
    assert first.headers["Cache-Control"] == "no-store"
    assert first.json() == client.get(exam + "/next-question", headers=owner).json()
    first_id = first.json()["question_id"]
    assert_error(
        client.post(
            exam + "/submit-answer",
            headers=owner,
            json={
                "submission_id": str(uuid4()),
                "question_id": first_id,
                "selected_index": 99,
            },
        ),
        422,
        "VALIDATION_FAILED",
    )
    issued = []
    for index in range(5):
        response = client.get(exam + "/next-question", headers=owner)
        assert response.status_code == 200, response.text
        question = response.json()
        assert {"correct_index", "explanation", "sources"}.isdisjoint(question)
        question_id = question["question_id"]
        assert question_id not in issued
        issued.append(question_id)
        if index == 2:
            assert question["difficulty"] == "Hard"
        right_index = keys[question_id]
        data = {
            "submission_id": str(uuid4()),
            "question_id": question_id,
            "selected_index": right_index
            if index < 2
            else (right_index + 1) % len(question["options"]),
        }
        response = client.post(exam + "/submit-answer", headers=owner, json=data)
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert {"correct_index", "explanation"}.isdisjoint(receipt)
        assert receipt == client.post(exam + "/submit-answer", headers=owner, json=data).json()
        assert_error(
            client.post(
                exam + "/submit-answer",
                headers=owner,
                json={
                    **data,
                    "selected_index": (data["selected_index"] + 1) % len(question["options"]),
                },
            ),
            409,
            "STATE_CONFLICT",
        )
        assert receipt["exam_completed"] is (index == 4)
    other = account(client, "other@example.com")
    assert_error(client.get(exam + "/report", headers=other), 404, "RESOURCE_NOT_FOUND")
    assert_error(client.get(exam + "/report", headers=owner), 409, "INVALID_EXAM_TRANSITION")
    graded = client.post(exam + "/grade", headers=owner)
    assert graded.status_code == 200, graded.text
    report = graded.json()
    assert report["correct_count"] == 2
    assert report["answered_count"] == 5
    assert report["score_ratio"] == 0.4
    assert len(report["review_sources"]) == 3
    assert report == client.get(exam + "/report", headers=owner).json()
    assert report == client.post(exam + "/grade", headers=owner).json()


def test_complete_early_and_preserve_frozen_pool(client, owner):
    document = add_document(client, owner)
    questions = generate(client, owner, document, question_count=1)["questions"]
    approve(client, owner, questions)
    exam = new_exam(client, owner, document)
    assert client.post(exam + "/start", headers=owner).status_code == 200
    question_id = questions[0]["question_id"]
    assert (
        client.post(
            f"/api/v1/questions/{question_id}/review", headers=owner, json={"status": "rejected"}
        ).status_code
        == 200
    )
    assert client.get(exam + "/next-question", headers=owner).json()["question_id"] == question_id
    assert client.post(exam + "/complete", headers=owner).json()["state"] == "Completed"
    result = client.post(exam + "/grade", headers=owner).json()
    assert result["completion_reason"] == "user_finished"
    assert result["score_ratio"] is None


def test_live_generation_and_invalid_citation_fallback(tmp_path, monkeypatch):
    real_client = httpx.AsyncClient
    cited_page = 1

    def provider(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        content = {
            "questions": [
                {
                    "prompt": "Which statement is grounded in the source?",
                    "options": [SOURCE.splitlines()[0], "The lesson is about color only."],
                    "correct_index": 0,
                    "explanation": "The first sentence is cited.",
                    "topic": "Architecture",
                    "sources": [{"page_number": cited_page, "excerpt": SOURCE.splitlines()[0]}],
                }
            ],
        }
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(content)}}]}
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(provider),
            **kwargs,
        ),
    )
    settings = Settings(
        ai_base_url="https://provider.example/v1", ai_api_key="test-key", ai_provider="test"
    )
    with TestClient(create_app(settings, database_path=tmp_path / "live.db")) as client:
        owner = account(client, "owner@example.com")
        document = add_document(client, owner)
        live = generate(client, owner, document, question_count=1, use_live=True)
        assert live["generation_mode"] == "live"
        assert live["fallback_reason"] is None
        cited_page = 99
        fallback = generate(client, owner, document, question_count=2, use_live=True)
        assert fallback["generation_mode"] == "mock"
        assert fallback["fallback_reason"]
        assert "test-key" not in fallback["fallback_reason"]
