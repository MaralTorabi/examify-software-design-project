# Examify — AI-Powered PDF Ingestion & Adaptive Exam Platform

**Examify** is an enterprise-grade, adaptive testing system built with Python 3.14+ that automatically ingests educational and reference PDF documents, extracts verifiable source material, generates grounded multiple-choice questions via modern AI adapters (with deterministic offline mock fallback), and conducts dynamic, adaptive student exam sessions.

---

## 1. Architectural Foundation — Layered Modular Monolith

Examify follows a strict **Layered Modular Monolith** architecture with single-direction dependency flow:

```
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway (`api/`)                     │
│  FastAPI Endpoints, Auth (JWT), Exception Envelope Filter   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              Application & Services (`services/`)           │
│  Ingestion (pypdf), AI Generation Subsystem, Adaptive Engine│
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  Domain Layer (`domain/`)                   │
│  Pure Entities, State Machine, Factory, Ports, Persistence  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   Core Layer (`core/`)                      │
│  Frozen Shared Contracts (Pydantic V2), Types, Errors, Conf │
└─────────────────────────────────────────────────────────────┘
```

### Core Dependency Rules
1. **`core/` is isolated and frozen**: Contains standard application exceptions, enumerations, configuration (`pydantic-settings`), and immutable Pydantic V2 data transfer contracts (`FrozenContract`). It imports nothing from outer layers.
2. **`domain/` contains pure business logic**: Entities, question factories (`QuestionFactory`), exam session lifecycle state machines (`ExamStateEnum`), and port interfaces.
3. **`services/` orchestrates workflows**:
   - `services/ingestion/`: Physical page-aware PDF extraction (1-indexed).
   - `services/ai/`: Decoupled `AIAdapter` interface with 3-stage quote validation, deterministic `OfflineMockAIAdapter`, and `FallbackAIAdapter`.
   - `services/adaptive/`: Strategy-pattern driven difficulty adaptation (`ConsecutiveAnswersStrategy`, `RollingAccuracyStrategy`).
4. **`api/` exposes HTTP transport**: Translates HTTP requests into domain/service invocations, enforces security/auth, and guarantees student-facing response models strictly redact answer keys and teacher explanations.

---

## 2. Python 3.14 Setup & Development Instructions

### Prerequisites
- **Python 3.14+**
- **Git**
- Recommended package manager: **uv** or standard **pip**

### Installation

Clone the repository and navigate into the project root:
```powershell
git clone https://github.com/MaralTorabi/examify-software-design-project.git
cd examify-software-design-project
```

#### Option A: Using `uv` (Recommended)
```powershell
uv venv
.venv\Scripts\activate
uv sync
```

#### Option B: Using standard Python `pip`
```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

### Running Tests
Execute the comprehensive contract, unit, and subsystem test suite:
```powershell
pytest
```

### Running Linter & Quality Gates
Enforce code formatting and contract integrity:
```powershell
ruff check .
```

---

## 3. Team Branching & RAD Strategy

The project baseline is anchored at tag `architecture-v1.0` on `main`. Team members work on decoupled feature branches:
- `feat/domain-persistence`: Domain models, database schema, State & Factory patterns.
- `feat/api-client-gateway`: FastAPI routes, auth dependency, student UI client.
- `feat/services-ai-adaptive`: AI generation pipelines, fallback adapter, adaptive strategies.
- `feat/services-ingestion`: PDF page-level parsing and validation.

All feature branches branch from and merge cleanly back into `main` against frozen `core/` contracts.
