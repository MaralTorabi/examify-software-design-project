import json
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from starlette.concurrency import run_in_threadpool

from api.auth import CurrentUser
from api.exception_handlers import UnsupportedFileError, UploadTooLargeError
from api.storage import read_document, save_document
from core.errors import AuthorizationError, NotFoundError, ValidationError
from core.schemas import ExtractedPage, GenerationRequest, StudentQuestionView
from core.types import Difficulty, ReviewStatus

router = APIRouter(prefix="/api/v1", tags=["documents"])
MAX_SOURCE_CHARACTERS = 200_000


class PastedText(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    text: Annotated[str, Field(min_length=1)]


class ShareRequest(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]


class GenerateQuestions(BaseModel):
    question_count: Annotated[int, Field(strict=True, ge=1, le=30)] = 8
    difficulty: Difficulty | None = None
    language: Literal["fa", "en"] = "fa"
    use_live: bool = False


class ReviewQuestion(BaseModel):
    status: Literal[ReviewStatus.APPROVED, ReviewStatus.REJECTED]


def visible_document(connection, doc_id, actor_id, *, owner_only=False):
    document = read_document(connection, doc_id)
    if document is None or (
        actor_id != document["owner_id"] and actor_id not in document["shared_with"]
    ):
        raise NotFoundError("Document not found.")
    if owner_only and actor_id != document["owner_id"]:
        raise AuthorizationError("Only the document owner can perform this action.")
    return document


def document_view(document, actor_id):
    return {
        **{
            key: document[key]
            for key in (
                "document_id",
                "title",
                "filename",
                "sha256",
                "size_bytes",
                "status",
                "page_count",
                "extracted_page_count",
                "uploaded_at",
            )
        },
        "is_owner": document["owner_id"] == actor_id,
        "question_count": len(document["questions"]),
        "approved_count": sum(
            item["review_status"] == "approved" for item in document["questions"]
        ),
    }


def save_source(request, actor_id, title, filename, raw_content, page_texts):
    if not any(text.strip() for text in page_texts):
        raise ValidationError("The document contains no extractable text.")
    if sum(map(len, page_texts)) > MAX_SOURCE_CHARACTERS:
        raise UploadTooLargeError("The extracted text exceeds the prototype limit.")
    doc_id = str(uuid4())
    document = {
        "document_id": doc_id,
        "owner_id": actor_id,
        "shared_with": [],
        "title": title,
        "filename": filename,
        "sha256": sha256(raw_content).hexdigest(),
        "size_bytes": len(raw_content),
        "status": "Ready",
        "page_count": len(page_texts),
        "extracted_page_count": sum(bool(text.strip()) for text in page_texts),
        "uploaded_at": datetime.now(UTC).isoformat(),
        "pages": page_texts,
        "questions": [],
    }
    with request.app.state.store.transaction(write=True) as connection:
        save_document(connection, document)
    return document_view(document, actor_id)


def extract_text(raw_content, extension, max_pages):
    if extension == ".txt":
        try:
            return [raw_content.decode("utf-8-sig")]
        except UnicodeDecodeError as exc:
            raise ValidationError("Text files must use UTF-8 encoding.") from exc
    try:
        reader = PdfReader(BytesIO(raw_content))
        if reader.is_encrypted:
            raise ValidationError("Password-protected PDFs are not supported.")
        if len(reader.pages) > max_pages:
            raise UploadTooLargeError("The PDF has too many pages.")
        pages = []
        extracted_characters = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            extracted_characters += len(page_text)
            if extracted_characters > MAX_SOURCE_CHARACTERS:
                raise UploadTooLargeError("The extracted text exceeds the prototype limit.")
            pages.append(page_text)
        return pages
    except (PdfReadError, ValueError, UnicodeError) as exc:
        raise ValidationError("The uploaded PDF could not be read.") from exc


@router.post("/documents/from-text", status_code=201)
def from_text(body: PastedText, request: Request, user: CurrentUser):
    title = body.title.strip()
    if not title:
        raise ValidationError("A title is required.")
    raw = body.text.encode("utf-8")
    if len(raw) > request.app.state.settings.max_pdf_size_bytes:
        raise UploadTooLargeError("The pasted text exceeds the upload limit.")
    return save_source(request, str(user.id), title, f"{title}.txt", raw, [body.text])


@router.post("/documents/upload", status_code=201)
def upload(request: Request, user: CurrentUser, file: Annotated[UploadFile, File()]):
    filename = Path((file.filename or "").replace(chr(92), "/")).name
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".txt"}:
        raise UnsupportedFileError("Upload a .pdf or .txt file.")
    settings = request.app.state.settings
    raw = file.file.read(settings.max_pdf_size_bytes + 1)
    if len(raw) > settings.max_pdf_size_bytes:
        raise UploadTooLargeError("The file exceeds the upload limit.")
    if not raw:
        raise ValidationError("The uploaded file is empty.")
    pages = extract_text(raw, extension, settings.max_pages)
    return save_source(request, str(user.id), Path(filename).stem, filename, raw, pages)


@router.get("/documents")
def list_documents(request: Request, user: CurrentUser):
    actor_id = str(user.id)
    with request.app.state.store.transaction() as connection:
        rows = connection.execute(
            """SELECT data FROM prototype_documents AS document
               WHERE json_extract(data, '$.owner_id') = ?
                  OR EXISTS (SELECT 1 FROM json_each(document.data, '$.shared_with') WHERE value = ?)
               ORDER BY json_extract(data, '$.uploaded_at') DESC""",
            (actor_id, actor_id),
        ).fetchall()
    return [document_view(json.loads(row["data"]), actor_id) for row in rows]


@router.get("/documents/{doc_id}")
def get_document(doc_id: UUID, request: Request, user: CurrentUser):
    with request.app.state.store.transaction() as connection:
        return document_view(visible_document(connection, doc_id, str(user.id)), str(user.id))


@router.post("/documents/{doc_id}/share")
def share_document(doc_id: UUID, body: ShareRequest, request: Request, user: CurrentUser):
    actor_id = str(user.id)
    email = body.email.strip().casefold()
    with request.app.state.store.transaction(write=True) as connection:
        document = visible_document(connection, doc_id, actor_id, owner_only=True)
        recipient = connection.execute(
            "SELECT id FROM prototype_users WHERE email = ?", (email,)
        ).fetchone()
        if recipient is None:
            raise NotFoundError("Recipient not found.")
        if recipient["id"] != actor_id and recipient["id"] not in document["shared_with"]:
            document["shared_with"].append(recipient["id"])
            save_document(connection, document)
    return {"document_id": doc_id, "shared_with": email}


def load_pages(request, doc_id, actor_id):
    with request.app.state.store.transaction() as connection:
        document = visible_document(connection, doc_id, actor_id, owner_only=True)
    return tuple(
        ExtractedPage(document_id=doc_id, page_number=number, text=text)
        for number, text in enumerate(document["pages"], 1)
        if text.strip()
    )


def citation_key(question):
    return tuple(
        (source["page_number"], " ".join(source["excerpt"].split()).casefold())
        for source in question["sources"]
    )


def append_questions(request, doc_id, actor_id, questions):
    with request.app.state.store.transaction(write=True) as connection:
        document = visible_document(connection, doc_id, actor_id, owner_only=True)
        existing_ids = {item["question_id"] for item in document["questions"]}
        existing_mock = {
            citation_key(item)
            for item in document["questions"]
            if item["generation_mode"] == "mock"
        }
        added = [
            item
            for item in questions
            if item["question_id"] not in existing_ids
            and (item["generation_mode"] != "mock" or citation_key(item) not in existing_mock)
        ]
        if added:
            document["questions"].extend(added)
            save_document(connection, document)
    return added


def format_mock_question(item, language):
    """Use a quotation with a blank so other true source statements are valid distractors."""
    source = item["sources"][0]
    words = source["excerpt"].split()
    start = len(words) // 3
    end = min(start + 3, len(words) - 1)
    answer = " ".join(words[start:end])
    sentence = " ".join([*words[:start], "…", *words[end:]])
    options = []
    used = set()
    correct_index = item["correct_index"]
    for index, option in enumerate(item["options"]):
        if index == correct_index:
            correct_position = len(options)
            options.append(answer)
            continue
        option_words = option.split()
        offset = len(option_words) // 3
        alternate = " ".join(option_words[offset : offset + end - start])
        normalized = alternate.casefold()
        if normalized != answer.casefold() and normalized not in used:
            used.add(normalized)
            options.append(alternate)
    if len(options) < 2:
        # Keep the alternate full statement when the short fragments are identical.
        alternate = next(option for i, option in enumerate(item["options"]) if i != correct_index)
        options.append(alternate)
    page = source["page_number"]
    if language == "fa":
        item["prompt"] = f"با توجه به متن صفحهٔ {page}، جای خالی را پر کنید. «{sentence}»"
        item["explanation"] = f"متن منبع در صفحهٔ {page} آمده است. «{source['excerpt']}»"
    else:
        item["prompt"] = f"Complete the quotation from page {page}. “{sentence}”"
    item["options"] = options
    item["correct_index"] = correct_position


@router.post("/documents/{doc_id}/generate-questions")
async def generate_questions(
    doc_id: UUID, request: Request, user: CurrentUser, body: GenerateQuestions | None = None
):
    body = body or GenerateQuestions()
    pages = await run_in_threadpool(load_pages, request, doc_id, str(user.id))
    service = (
        request.app.state.live_generation if body.use_live else request.app.state.offline_generation
    )
    generation_request = GenerationRequest(
        document_id=doc_id,
        pages=pages,
        question_count=body.question_count,
        difficulty=body.difficulty or Difficulty.MEDIUM,
        language=body.language,
        seed={None: 0, Difficulty.EASY: 1, Difficulty.MEDIUM: 2, Difficulty.HARD: 3}[
            body.difficulty
        ],
    )
    batch = await service.generate(user.id, generation_request)
    questions = []
    seen = set()
    for question in batch.questions:
        item = question.model_dump(mode="json")
        key = citation_key(item)
        if key in seen:
            continue
        seen.add(key)
        if question.generation_mode == "mock":
            if body.difficulty is None:
                demo_levels = (
                    Difficulty.MEDIUM,
                    Difficulty.MEDIUM,
                    Difficulty.HARD,
                    Difficulty.EASY,
                )
                item["difficulty"] = demo_levels[len(questions) % len(demo_levels)]
            format_mock_question(item, body.language)
        item["review_status"] = ReviewStatus.PENDING
        questions.append(item)
    added = await run_in_threadpool(append_questions, request, doc_id, str(user.id), questions)
    warnings = list(batch.warnings)
    if len(added) < len(batch.questions):
        warnings.append("Duplicate or previously generated questions were skipped.")
    return {
        "generation_mode": batch.generation_mode,
        "provider": batch.provider,
        "fallback_reason": batch.fallback_reason,
        "warnings": warnings,
        "questions": added,
    }


@router.get("/documents/{doc_id}/questions")
def list_questions(doc_id: UUID, request: Request, user: CurrentUser):
    actor_id = str(user.id)
    with request.app.state.store.transaction() as connection:
        document = visible_document(connection, doc_id, actor_id)
    if document["owner_id"] == actor_id:
        return document["questions"]
    return [
        StudentQuestionView.model_validate(
            {
                key: item[key]
                for key in (
                    "question_id",
                    "prompt",
                    "options",
                    "difficulty",
                    "topic",
                )
            }
        ).model_dump(mode="json")
        for item in document["questions"]
        if item["review_status"] == ReviewStatus.APPROVED
    ]


@router.post("/questions/{question_id}/review")
def review_question(question_id: UUID, body: ReviewQuestion, request: Request, user: CurrentUser):
    with request.app.state.store.transaction(write=True) as connection:
        row = connection.execute(
            """SELECT data FROM prototype_documents AS document
               WHERE EXISTS (SELECT 1 FROM json_each(document.data, '$.questions') AS question
                             WHERE json_extract(question.value, '$.question_id') = ?)""",
            (str(question_id),),
        ).fetchone()
        if row is None:
            raise NotFoundError("Question not found.")
        document = visible_document(
            connection, json.loads(row["data"])["document_id"], str(user.id), owner_only=True
        )
        question = next(
            item for item in document["questions"] if item["question_id"] == str(question_id)
        )
        question["review_status"] = body.status
        save_document(connection, document)
    return {"question_id": question_id, "review_status": body.status}
