# Contributing to AcuCalyx

Thank you for your interest in contributing to **AcuCalyx**! AcuCalyx is a clinical-grade, open-source computational planning and rehearsal system for Percutaneous Nephrolithotomy (PCNL) needle access and virtual fluoroscopy simulation.

Because AcuCalyx models surgical corridors, tissue puncture trajectories, and anatomical landmarks, we maintain rigorous engineering, mathematical, and medical device software standards (IEC 62304 / ISO 14971 principles).

Please take a few moments to review these guidelines before submitting code, documentation, or issue reports.

---

## Table of Contents

1. [Medical Ethics & Zero-PHI Policy](#1-medical-ethics--zero-phi-policy)
2. [Collaboration Models: Teammates vs. External Contributors](#2-collaboration-models-teammates-vs-external-contributors)
3. [Local Development Setup](#3-local-development-setup)
4. [Branching & Development Workflow](#4-branching--development-workflow)
5. [Conventional Commits Standard](#5-conventional-commits-standard)
6. [Testing & Quality Verification Gates](#6-testing--quality-verification-gates)
7. [Engineering & Code Standards](#7-engineering--code-standards)
8. [Pull Request (PR) Checklist](#8-pull-request-pr-checklist)

---

## 1. Medical Ethics & Zero-PHI Policy

> [!CAUTION]
> **STRICT ZERO PROTECTED HEALTH INFORMATION (PHI) POLICY**
> Under NO circumstances should real patient data, identifiable DICOM files, medical record numbers (MRNs), patient names, birth dates, or clinical accession identifiers be committed to this repository.

* **De-Identification Requirement:** All test datasets, fixtures, and clinical examples MUST be generated synthetically (using `tests/phantom/` generators) or processed through `PHIGuard` DICOM PS 3.15 de-identification prior to use.
* **Local Test Scans:** Local real-world development datasets must be placed in `data/cases/` or paths listed in `.gitignore`. Never use `git add -f` to force-track medical image volumes.
* **Safety & Hazard Impact:** Any modification to trajectory optimization (`src/acucalyx/planning/`), hazard detection (`src/acucalyx/hazards/`), or DRR metrology (`src/acucalyx/drr/`) must include automated verification tests to ensure patient safety thresholds are preserved.

---

## 2. Collaboration Models: Teammates vs. External Contributors

Depending on your access level, choose the appropriate contribution model:

### A. Core Team Members (Collaborators with Write Access)
1. **Direct pushes to `main` are restricted.** All changes must enter `main` through a Pull Request.
2. Clone the central repository directly:
   ```bash
   git clone https://github.com/Tejas3479/AcuCalyx.git
   cd AcuCalyx
   ```
3. Create a dedicated feature or bugfix branch on the primary repository:
   ```bash
   git checkout -b feat/your-feature-name
   ```
4. Push your branch and open a Pull Request against `main`.

### B. External Open Source Contributors (Fork & PR)
1. Fork the repository to your personal GitHub account by clicking the **Fork** button on GitHub.
2. Clone your personal fork locally:
   ```bash
   git clone https://github.com/<YOUR-USERNAME>/AcuCalyx.git
   cd AcuCalyx
   git remote add upstream https://github.com/Tejas3479/AcuCalyx.git
   ```
3. Create a descriptive feature branch:
   ```bash
   git checkout -b feat/your-feature-name
   ```
4. Push your branch to your fork and open a Pull Request against `Tejas3479/AcuCalyx:main`.

---

## 3. Local Development Setup

### Prerequisites
* **Python 3.10+** (Python 3.11, 3.12, or 3.13 recommended)
* **Git 2.30+**
* Web browser with WebGL2 support (Chrome, Firefox, Edge, Safari)

### Step-by-Step Installation

1. **Create and Activate a Virtual Environment:**
   * **Windows (PowerShell):**
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   * **Linux / macOS:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

2. **Install Dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Verify the Installation:**
   Run the test suite to confirm all components are operational:
   ```bash
   python -m pytest tests/unit tests/golden tests/integration tests/property
   ```
   *(All 240 tests should pass).*

4. **Start the Development Server:**
   ```bash
   python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   Navigate to `http://localhost:8000` to interact with the surgical rehearsal cockpit.

---

## 4. Branching & Development Workflow

Always branch off the latest `main` branch:

```bash
# Ensure your local main is up-to-date
git checkout main
git pull origin main

# Create a scoped feature branch
git checkout -b feat/fluoroscopy-depth-guide
```

### Branch Naming Conventions
Use descriptive, lower-case, hyphen-separated branch names prefixed with the purpose:
* `feat/` — New feature or algorithm (e.g., `feat/monopolar-cautery-hazard`, `feat/c-arm-laser-guide`)
* `fix/` — Bug fix or calculation repair (e.g., `fix/drr-principal-point-offset`, `fix/laterality-toggle-binding`)
* `docs/` — Documentation updates (e.g., `docs/clinical-workflow-guide`, `docs/api-specifications`)
* `test/` — Adding or refactoring unit, golden, or property tests (e.g., `test/staghorn-stone-fixture`)
* `refactor/` — Code cleanup or structural improvement with no behavior change (e.g., `refactor/mpr-slicing-cache`)
* `perf/` — Performance optimization (e.g., `perf/ray-marching-cuda-fallback`)

---

## 5. Conventional Commits Standard

We adhere to the [Conventional Commits 1.0.0](https://www.conventionalcommits.org/) specification. Each commit message should follow this format:

```text
<type>(<scope>): <short description in imperative mood>

[optional body explaining context, rationale, and clinical/technical trade-offs]

[optional footer(s), e.g. Closes #12]
```

### Commit Types
* `feat`: A new user-facing feature or algorithmic capability
* `fix`: A bug fix or defect resolution
* `docs`: Documentation-only additions or modifications
* `test`: Adding missing tests or correcting existing tests
* `refactor`: Code change that neither fixes a bug nor adds a feature
* `perf`: Code change that improves performance or latency
* `chore`: Maintenance tasks, dependency updates, CI/CD configs

### Recommended Scopes
* `pipeline`: Core planning orchestrator (`src/acucalyx/pipeline.py`)
* `planning`: Needle trajectory corridors & Pareto optimizer (`src/acucalyx/planning/`)
* `hazards`: Critical organ collision & hazard engines (`src/acucalyx/hazards/`)
* `drr`: Virtual fluoroscopy & DRR projection simulation (`src/acucalyx/drr/`)
* `ultrasound`: Multimodal B-mode ultrasound, NAVI & covariance (`src/acucalyx/ultrasound/`)
* `endoscopy`: Flexible/rigid scope kinematics & reachability (`src/acucalyx/endoscopy/`)
* `integrations`: TotalSegmentator, nnU-Net, Slicer bridges (`src/acucalyx/integrations/`)
* `api`: FastAPI backend endpoints & middleware (`app/api/`)
* `frontend`: HTML5, Three.js 3D viewport, MPR viewer (`app/frontend/`)
* `coords`: Physical LPS coordinate transformations (`src/acucalyx/coordinates.py`)
* `phi`: DICOM PS 3.15 de-identification guard (`src/acucalyx/dicom/`)

### Examples of Good Commit Messages
```bash
feat(planning): add fail-safe 3-tier Pareto optimizer with fallback guarantee
fix(frontend): bind laterality selector directly to active planning pipeline
test(golden): add high-riding kidney supracostal intercostal golden challenge
docs(readme): document clinical interlocks and dual-monitor cockpit controls
```

---

## 6. Testing & Quality Verification Gates

AcuCalyx enforces a zero-regression policy. **All 240 tests must pass** prior to any merge into `main`.

### Running Tests

```bash
# Run the complete test suite
python -m pytest tests/unit tests/golden tests/integration tests/property

# Run a specific test directory
python -m pytest tests/unit
python -m pytest tests/golden

# Run a specific test module with verbose output
python -m pytest tests/unit/test_pareto.py -v

# Run with coverage report
python -m pytest --cov=src/acucalyx tests/unit
```

### Test Suite Structure
1. **Unit Tests (`tests/unit/` - 216 tests):** Validate single-function invariants, coordinates, DICOM parsers, ultrasound simulation, endoscopic reachability, and hazard calculators in isolation.
2. **Golden Challenge Cases (`tests/golden/` - 19 tests):** Stress-test planning algorithms against complex anatomical scenarios (e.g., retrorenal colon, staghorn calculus, severe hydronephrosis).
3. **Property-Based Invariants (`tests/property/` - 4 tests):** Use Hypothesis to fuzz continuous coordinate transformations and SE(3) distance invariances across edge cases.
4. **Procedural Integration (`tests/integration/` - 1 test):** Validates the entire pipeline from phantom generation through stone volumetry, Pareto optimization, DRR fluoroscopy, and PDF generation.

---

## 7. Engineering & Code Standards

### Python Standards
* Target Python `>= 3.10`.
* Use explicit type annotations for function signatures.
* Write clear docstrings documenting input coordinates, reference frames, and units:
  * **Distances:** Millimeters (`mm`).
  * **Angles:** Degrees (`°`) or Radians (`rad`) — always explicitly stated in parameter names (e.g., `alpha_deg`, `theta_rad`).
  * **Densities:** Hounsfield Units (`HU`).
  * **Coordinate Space:** LPS physical coordinates (`[x, y, z]` where $+x$ is Left, $+y$ is Posterior, $+z$ is Superior).
* Avoid global state or non-thread-safe singletons.

### Frontend Standards
* Pure Vanilla JavaScript (ES6+), HTML5, and standard CSS3.
* Keep 3D scene rendering decoupled from DOM event management.
* Maintain clean memory lifecycle in Three.js (dispose of geometries, materials, and textures when switching cases).
* Test responsive viewports across standard clinical monitor resolutions ($1920 \times 1080$, $2560 \times 1440$).

---

## 8. Pull Request (PR) Checklist

Before submitting your Pull Request, verify that you have completed each item:

- [ ] **Zero PHI:** Checked the git diff (`git diff HEAD~1`) to guarantee no real patient DICOM, scan volumes, or clinical identifiers are committed.
- [ ] **Tests Pass:** Executed `python -m pytest tests/unit tests/golden tests/integration tests/property` and verified 100% pass rate.
- [ ] **New Tests Added:** Written unit or golden tests for any newly introduced algorithms, hazards, or endpoints.
- [ ] **Coordinate Conventions:** Verified that all 3D points adhere to LPS physical coordinates in millimeters.
- [ ] **Clean Git History:** Commit messages follow the [Conventional Commits](#5-conventional-commits-standard) format.
- [ ] **Documentation Updated:** Updated `README.md`, docstrings, or relevant architectural docs in `docs/` if modifying APIs or configurations.
- [ ] **Working Tree Clean:** No stray temporary files, cache artifacts, or editor settings (`.vscode`, `.idea`, `.DS_Store`).

### PR Review Process
1. Once opened, a maintainer will review your code for clinical safety, mathematical correctness, test coverage, and architecture.
2. Address any requested changes by pushing additional commits to your branch.
3. Once approved and all CI checks pass, your branch will be merged into `main`.

Thank you for helping make surgical renal access safer, faster, and more precise!
