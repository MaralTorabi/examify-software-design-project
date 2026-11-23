# Examify — 1-Hour Prototype & Metrics Sprint Task List

> [!IMPORTANT]
> **Strict Concurrency Rule**: Each team member (or their AI agent) must work strictly inside their assigned folders/branch, replace `[ ]` with `[x]` ONLY in their own section upon completing each task, and commit/push so Git auto-merges cleanly without conflicts.

**Goal**: Deliver a live, runnable prototype (supporting direct pasted text & `.pdf`/`.txt` upload -> deterministic offline AI question generation -> adaptive exam -> analytics report) and maximize `LOC` and `Function Point` metrics on `main`.

---

## 60-Minute Timeline Overview

| Phase | Timeframe | Key Action & Milestone Deliverable |
| :--- | :--- | :--- |
| **Phase 1** | **Min 00–05** | **Sync & Branch**: Pull latest `main` (`git pull origin main`) and branch off into assigned isolated feature branches. |
| **Phase 2** | **Min 05–40** | **Parallel Construction**: Deep implementation + unit tests + checking off `[x]` in assigned section below. |
| **Phase 3** | **Min 40–50** | **Integration Sync**: Push feature branches and merge all 4 branches into `main` cleanly. |
| **Phase 4** | **Min 50–60** | **Verification & Demo**: Run full `pytest`, launch `uvicorn api.main:app --reload`, verify live browser demo, Swagger UI (`/docs`), and `docs/FUNCTION_POINT_REPORT.md`. |

---

## Parallel Member Task Assignments (4 Laptops)

### Section 1: Maral (40213312) — Branch `feat/services-core`
**Scope:** `services/ingestion/`, `services/adaptive/`, `tests/services/`

- [ ] Implement `ContentExtractionService` in `services/ingestion/extractor.py` (supporting both `extract_from_text` for pasted text and `extract_from_bytes` for `.pdf`/`.txt` with 1-indexed pages & SHA-256).
- [ ] Implement `ConsecutiveAnswersStrategy`, `RollingAccuracyStrategy`, and `AdaptiveQuestionSelector` in `services/adaptive/`.
- [ ] Write unit tests in `tests/services/test_ingestion_and_adaptive.py` and verify `pytest` passes.
- [ ] Mark tasks `[x]` and push `origin feat/services-core`.

---

### Section 2: Fatemeh (40312033) — Branch `feat/domain-persistence`
**Scope:** `domain/`, `tests/domain/`

- [ ] Implement `MultipleChoiceQuestionFactory` (`domain/patterns/question_factory.py`) and `ExamState` state machine (`domain/patterns/exam_states.py`).
- [ ] Implement SQLite WAL database setup + `init_db()` (`domain/persistence/database.py`) and all 11 SQLAlchemy ORM tables (`domain/persistence/models.py`) for Function Point ILF count.
- [ ] Implement repositories, `SQLAlchemyUnitOfWork` (with optimistic locking `version`), `ExamApplicationService`, and `AnalyticsService`.
- [ ] Write unit tests in `tests/domain/test_domain_prototype.py`, mark tasks `[x]`, and push `origin feat/domain-persistence`.

---

### Section 3: Arshia (40313402) — Branch `feat/api-gateway`
**Scope:** `api/`, `tests/api/`

- [ ] Implement `api/auth.py` (Argon2 + PyJWT) and `api/exception_handlers.py` (standard JSON error envelope).
- [ ] Implement routes in `api/routes/` (`health.py`, `auth.py`, `documents.py` including `/from-text` & `/upload`, and `exams.py` ensuring `correct_index` is redacted).
- [ ] Wire dependencies, startup `init_db()`, CORS, and static `/client` serving in `api/bootstrap.py` & `api/main.py`.
- [ ] Write API tests in `tests/api/test_api_prototype.py`, mark tasks `[x]`, and push `origin feat/api-gateway`.

---

### Section 4: Member 4 (Frontend & FP Docs) — Branch `feat/client-ui`
**Scope:** `client/`, `docs/`, `tests/e2e/`

- [ ] Build Persian RTL (`dir="rtl"`) 4-step interactive prototype UI in `client/index.html`, `client/style.css`, and `client/app.js` (Login -> Paste Text/Upload -> Adaptive Exam -> Report).
- [ ] Create IFPUG Function Point calculation report in `docs/FUNCTION_POINT_REPORT.md` (11 ILFs, 2 EIFs, 12 EIs, 3 EOs, 5 EQs).
- [ ] Write end-to-end offline flow test in `tests/e2e/test_full_prototype_flow.py`, mark tasks `[x]`, and push `origin feat/client-ui`.
