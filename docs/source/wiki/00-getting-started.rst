00 — Getting started: Local deployment and operations
=========================================================

Every other page in this wiki (:doc:`index`) answers *why* -- engineering rationale, grounded in
the code. This page is the one deliberate exception: a practical, ordered walkthrough for going
from a bare checkout to a running app, a passing test suite, and real reports on disk. It doesn't
replace the pages it draws from -- it's the connective narrative across them, so a new reader
doesn't have to assemble the sequence themselves from README, :doc:`../operations`, and :doc:`../qa`
separately. Every command below was run for real against this repository while writing this page,
not assumed.

If a command block here ever looks stale, the source of truth for that specific piece is named
alongside it -- check there first.

1. Prerequisites
--------------------

- **Python 3.12** -- required exactly, not "3.12 or later": the pinned PyTorch/CUDA wheel set
  targets this interpreter specifically (see :doc:`02-tools-and-stack`).
- **git**, to clone the repository.
- **Ollama** (`ollama.com <https://ollama.com>`_), running locally -- every generation call in this
  project goes through it; there is no paid-API code path (the agent instructions SS1).
- **Optional: an NVIDIA GPU + CUDA drivers.** The app runs on CPU too (slower embedding/NLI/spaCy
  calls); Windows installs a CUDA-specific PyTorch build by default (step 2 below), Ubuntu's lock
  file does the equivalent.
- **Optional: Neo4j + a JDK** -- only needed for the standalone knowledge-graph explorer (section 4
  below). Every other page of the app works with zero Neo4j setup.

2. Environment setup from scratch
--------------------------------------

Source of truth: the repository's ``README.MD``, **Services -> Installation & Setup** section --
reproduced here so the walkthrough doesn't require tab-switching, kept word-for-word identical to
avoid the two copies drifting apart.

**Windows 11** (PowerShell or Command Prompt)::

    python -m pip install --user tox pip-tools
    py -3.12 -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 --no-cache-dir
    pip install -r requirements-base.txt
    python -c "import nltk; nltk.download('vader_lexicon'); nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('brown'); nltk.download('averaged_perceptron_tagger_eng')"
    python -m spacy download en_core_web_sm
    copy config\config.ini.example config\config.ini

**Ubuntu**::

    sudo apt update && sudo apt install pipx python3-venv -y
    pipx install tox
    pipx install pip-tools
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements-base.txt -r requirements-linux.txt
    python -c "import nltk; nltk.download('vader_lexicon'); nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('brown'); nltk.download('averaged_perceptron_tagger_eng')"
    python -m spacy download en_core_web_sm
    cp config/config.ini.example config/config.ini

.. warning::
   ``requirements-linux.txt`` is a **disclosed, unfixed gap** (last regenerated 2026-06-22, before
   the FastAPI rewrite -- ``fastapi``/``sqlalchemy`` and ~30 other packages are simply absent from
   it). The Ubuntu install command above may fail to resolve or install a stale set on a fresh
   machine. See :doc:`02-tools-and-stack`'s disclosed-gaps section for the full finding and the
   exact fix (regenerate on real Ubuntu, not fixable from this Windows dev machine).

.. warning::
   The ``config/config.ini`` step above is **not optional, and not just for Neo4j** --
   ``config/config.ini`` is gitignored (it can hold a real Neo4j password) and
   ``utils/config_loader_short.py`` raises ``FileNotFoundError`` at *import time* if it's missing.
   Since that module is imported by nearly everything (``OllamaClient``, ``JSONLStore``, the
   status checks, ...), a fresh clone that skips this step fails to even start ``uvicorn`` --
   confirmed directly, not assumed: this was found while verifying that a fresh clone of this
   repository actually reaches a working state. The example file's real, working defaults need no
   edits beyond the ``[neo4j]`` password, and only if you're using ``/knowledge_graph``.

**Verify the install**::

    python -c "import fastapi, sqlalchemy, torch; print('torch CUDA available:', torch.cuda.is_available())"

Dependency changes always go through ``requirements.in`` -> ``pip-compile`` -- never hand-edit a
generated ``requirements-*.txt`` file (see :doc:`02-tools-and-stack`).

3. Running the app: backend and frontend
---------------------------------------------

There is no separate frontend build step in this project -- FastAPI serves the API *and* the
Jinja2+HTMX pages from the same process (see :doc:`01-architecture` for why: server-rendered
fragments, no npm/webpack/vite, no client SPA). "Start the backend" and "spin up the frontend" are
the same command:

**1. Start Ollama first** (every page that generates text needs it running)::

    ollama serve
    ollama pull tinyllama:latest

**2. Start the app**::

    uvicorn api.app:app --reload

Open http://127.0.0.1:8000/ -- the landing page links to every page (full table in :doc:`../index`'s
*UI layers* section). ``--reload`` watches source files and restarts on change; drop it for anything
resembling a long-running check.

**3. (Optional) CLI batch runner** -- no browser, same underlying ``ExperimentRunner``::

    python -m cli.run_experiment --config cli/example_config.toml

**Update, 2026-09-05:** the Neo4j knowledge-graph explorer used to be a separate Streamlit process
(``streamlit run run_knowledge_graph.py``). It's fully migrated now -- ``/knowledge_graph`` is a
page in the same FastAPI app as everything else, no second process to start. It still needs a real
Neo4j server running (see section 4 below), and degrades to a clear inline error if that server
isn't reachable, but there is no longer a separate UI to launch for it.

For an actual walkthrough of *using* the running app -- filling in the experiment form, watching
live progress, reading the result -- see :doc:`../operations`'s two full scenarios (UI and raw API).
This page stops at "the process is up and responding."

4. Service manipulations
------------------------------

**Ollama** -- the one service every page depends on:

.. code-block:: bash

   ollama serve                # start the server
   ollama pull mistral:7b      # download a model (recommended: qwen, phi3, tinyllama, llama3)
   ollama list                 # see what's downloaded
   ollama rm <model>           # free disk space

Windows: check the process is actually up with ``Get-Process ollama``. Linux/macOS:
``ps aux | grep ollama``, ``pkill ollama`` to kill a stuck one.

**Neo4j** -- only needed for the ``/knowledge_graph`` page; every other page works without it.
Full install/config/troubleshooting steps (community-edition install, ``config/config.ini``'s
``[neo4j]`` section, connectivity verification, stop/status commands for both OSes) are in
README.MD's **Services -> Neo4j setup** section -- not duplicated here since it's a self-contained,
opt-in procedure with its own troubleshooting branch, not part of the day-to-day loop.

Known Windows-specific pitfalls (2026.x / 5.x, confirmed from real setup 2026-10-27):

- ``JAVA_HOME`` and ``NEO4J_HOME`` must point to the **root**, not ``\\bin``. Both variables are
  appended with ``\\bin`` internally by ``neo4j.bat`` -- including ``\\bin`` in the variable produces
  a double ``\\bin\\bin`` path and ``ClassNotFoundException: org.neo4j.server.startup.Neo4jCommand``.
- The service-install command **changed** in 5.x / 2026.x:
  ``neo4j.bat windows-service install`` (the old ``neo4j install-service`` no longer works).
- Set ``neo4j_exe`` in ``config/config.ini``'s ``[neo4j]`` section to the full path of ``neo4j.bat``
  so the app's Start/Stop buttons work even when uvicorn was started before the PATH change took
  effect (see README's Neo4j setup step 3 for the exact config key).

**A real, previously-encountered gotcha worth knowing before it costs you time:** a stray
``uvicorn`` process left running from an earlier session can hold an OS-level lock on
``torch/_C.*.pyd`` (Windows) and silently break a later ``pip install --upgrade`` of ``torch`` with
an ``Access is denied`` error that looks like a packaging problem but isn't one. If a
``pip install``/``pip-compile`` step involving ``torch`` fails oddly, check for and kill orphaned
processes first:

.. code-block:: powershell

   Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%uvicorn%'" |
     ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

5. Troubleshooting: when the app or PC hangs
--------------------------------------------------

Real findings from actually diagnosing a live freeze during a heavy multi-student sweep (5 students,
RAG enabled, 500 tasks), not a generic checklist -- Task Manager's GPU tab showed the real cause
directly: **8.0 GB dedicated VRAM essentially full, and the GPU spilling into shared (system) GPU
memory.** That spillover -- system RAM being borrowed as VRAM -- is what actually causes a
full-system freeze, not high CPU (in the diagnosed case CPU sat at 21%, nowhere near the bottleneck).
Once VRAM overflows into shared memory, everything touching the GPU stalls, including the desktop
itself, not just this app.

**Why this app in particular can hit that ceiling**: several things want GPU memory at once --
whichever Ollama student model is currently active (several GB for a 7B-class model), the RAG
embedder (``all-MiniLM-L6-v2``), and -- if RAG is enabled -- the Layer 2 NLI cross-encoder for
hallucination checking. None of the app's own embedding/NLI models pin themselves to CPU; both
default to CUDA whenever it's available. ``ExperimentRunner``'s sweep loop iterates ``student`` as
the *outermost* loop (confirmed in ``core/services/experiment_runner.py``), so Ollama only swaps
the active model once per student, not per task -- that part is already efficient; the pressure
comes from concurrent residents, not needless swapping.

**What to actually do:**

1. **Check the GPU tab in Task Manager first** (or ``nvidia-smi`` on Linux) -- dedicated memory near
   its cap plus non-zero "shared GPU memory" is the freeze signature. If you see it, the machine is
   still technically alive, just extremely slow; give it time to finish the current request rather
   than force-killing mid-write if you can afford to wait.
2. **If you do need to kill it**, the JSONL store appends one line per response as it completes --
   killing mid-response loses at most the one in-flight write, never corrupts earlier rows. Killing
   is safe; it just isn't graceful.
3. **Levers to reduce VRAM pressure for future heavy runs** (not applied by default -- pick based on
   your hardware):

   - ``OLLAMA_MAX_LOADED_MODELS=1`` (a real Ollama environment variable) -- forces strict
     single-model residency, removing any brief overlap at a student-swap boundary.
   - Force the embedder/NLI cross-encoder onto CPU (``SentenceTransformer(model_name,
     device="cpu")`` / ``CrossEncoder(model_name, device="cpu")`` in
     ``core/analysis/calculate_advanced_linguistic_metrics.py``,
     ``core/adapters/rag/vector_store.py``, ``core/analysis/hallucination_check.py``) -- trades a
     little speed for freeing that VRAM entirely for Ollama. Worth it specifically for a heavy,
     RAG-enabled, multi-student sweep on an 8 GB card; not a default change, since it costs real
     throughput on a machine with room to spare.
   - Reduce the sweep size itself (fewer students per run, run them as separate smaller batches
     instead of one 500-task sweep) -- the existing ``max_total_tasks`` cap in
     ``config/config.ini``'s ``[EXPERIMENT]`` section is a blunt version of this; splitting a big
     sweep into several smaller ones spreads the same total work across separate model-residency
     windows instead of one long one.

**Restarting each service cleanly:**

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Service
     - How to restart
   * - FastAPI app
     - ``Ctrl+C`` in its terminal, then re-run ``uvicorn api.app:app --reload``. If that terminal is
       gone, find and kill it first (see the orphaned-process command in *Service manipulations*
       above), then start fresh.
   * - Ollama
     - Windows: check with ``Get-Process ollama``, kill via Task Manager or
       ``Stop-Process -Name ollama -Force`` if unresponsive, then ``ollama serve`` again.
       Linux/macOS: ``pkill ollama``, then ``ollama serve``.
   * - Neo4j
     - Only relevant if you're using the ``/knowledge_graph`` page. Full stop/status commands for
       both OSes are in README.MD's **Services -> Neo4j setup** section (step 4,
       troubleshooting) -- not duplicated here.

**Update, 2026-09-05: this app now has a real persistent log file.** ``api/app.py`` wires up a
loguru file sink at import time (``logs/lab_debug.log``, 10 MB rotation, 10-day retention -- the
same convention the legacy Streamlit app already used, so both eras share one place and format).
It does **not** call ``logger.remove()`` first, so console output (visible in whichever terminal
launched ``uvicorn``) keeps working alongside the file -- you don't lose live scrollback to get
persistence. Redirecting output at launch is no longer necessary just to keep a record, though it's
still a reasonable thing to do for a specific investigation::

    uvicorn api.app:app --reload > app_output.log 2>&1

6. Running tests
--------------------

.. code-block:: bash

   pytest tests --ignore=tests/e2e -v      # unit + integration + legacy_rag
   pytest tests/e2e -v                     # Playwright E2E -- ALWAYS a separate invocation
   pytest tests/legacy_rag/test_rag.py::test_valid_domains -v   # one test

   # tox envs (Windows):
   tox -e py312                            # full run: pytest + coverage + Allure + pytest-html
   tox -e e2e                              # Playwright E2E tox env (installs chromium first)
   tox -e lint                             # ruff + mypy + black --check
   tox -e format                           # apply black (the fixing counterpart of lint's --check)
   tox -e traceability                     # requirement-traceability gate (no tests executed)
   tox -e docs                             # Sphinx docs build only
   tox -e full                             # tests + traceability + Sphinx docs in one call (Windows)

   # tox envs (Ubuntu only):
   tox -e linux-full                       # unit + integration + e2e + traceability in one run

**Full test + artifacts + Sphinx docs pipeline — Windows 11 (verified 2026-10-27):**

Run from the repo root, in the activated ``.venv``. Steps must be executed in this order:
``generate_test_results_rst`` reads the ``junit.xml`` that pytest produces -- run it before
pytest and it exits with "no junit.xml found."

.. code-block:: powershell

   # Step 1: run tests, generate all report artifacts
   pytest `
     --html=results/pytest_test_results/pytest_report.html --self-contained-html `
     --junitxml=results/pytest_test_results/junit.xml `
     --alluredir=results/allure-results --clean-alluredir `
     --cov=core --cov=api --cov=cli --cov=web --cov=utils `
     --cov-report=term-missing `
     --cov-report=html:results/coverage_html `
     --cov-report=json:results/coverage.json `
     tests --ignore=tests/e2e -v

   # Step 2: regenerate QA RST pages from the live test suite + junit.xml results
   python -m utils.generate_qa_roster         # docs/source/_qa_test_roster.rst
   python -m utils.generate_test_results_rst  # docs/source/qa/test_results.rst

   # Step 3: build Sphinx docs (reads the freshly regenerated RST files)
   sphinx-build docs/source docs/source/_build/html

One-liner (PowerShell semicolons, runs all three steps sequentially)::

   pytest --html=results/pytest_test_results/pytest_report.html --self-contained-html --junitxml=results/pytest_test_results/junit.xml --alluredir=results/allure-results --clean-alluredir --cov=core --cov=api --cov=cli --cov=web --cov=utils --cov-report=term-missing --cov-report=html:results/coverage_html --cov-report=json:results/coverage.json tests --ignore=tests/e2e -v; python -m utils.generate_qa_roster; python -m utils.generate_test_results_rst; sphinx-build docs/source docs/source/_build/html

.. warning::
   **Ubuntu equivalent — NOT VERIFIED on Linux** (``requirements-linux.txt`` gap noted in section 2
   still applies; treat as aspirational until a real Ubuntu run confirms it):

   .. code-block:: bash

      # Step 1: run tests, generate all report artifacts
      pytest \
        --html=results/pytest_test_results/pytest_report.html --self-contained-html \
        --junitxml=results/pytest_test_results/junit.xml \
        --alluredir=results/allure-results --clean-alluredir \
        --cov=core --cov=api --cov=cli --cov=web --cov=utils \
        --cov-report=term-missing \
        --cov-report=html:results/coverage_html \
        --cov-report=json:results/coverage.json \
        tests --ignore=tests/e2e -v

      # Step 2: regenerate QA RST pages
      python -m utils.generate_qa_roster
      python -m utils.generate_test_results_rst

      # Step 3: build Sphinx docs
      sphinx-build docs/source docs/source/_build/html

``tests/e2e`` must never share a process with the rest of the suite: ``pytest-playwright``'s sync
driver leaves the main-thread asyncio event loop unusable for anything that later calls
``asyncio.run()`` directly -- confirmed empirically, not a theoretical concern (see :doc:`06-qa-testing-strategy`).
``tox -e py312`` (Windows) and ``tox -e linux-full`` (Ubuntu) both pass ``--ignore=tests/e2e``
for the unit/integration run and invoke Playwright in a separate process for exactly this reason.

7. Generating and viewing reports
---------------------------------------

``tox -e py312`` (above) produces all three of these in one run:

.. list-table::
   :widths: 25 35 40
   :header-rows: 1

   * - Report
     - Location
     - View with
   * - pytest-html
     - ``results/pytest_test_results/pytest_report.html``
     - Open directly in a browser
   * - Coverage (HTML)
     - ``results/coverage_html/index.html``
     - Open directly in a browser
   * - Allure results (raw)
     - ``results/allure-results/``
     - ``allure serve results/allure-results`` (live) or
       ``allure generate results/allure-results -o results/allure-report --clean`` (static copy)

Two QA utility scripts feed the Sphinx QA section with live, generated data (both run from the
repo root, after a pytest run that produced ``results/pytest_test_results/junit.xml``):

- ``python -m utils.generate_qa_roster`` -- rewrites ``docs/source/_qa_test_roster.rst``, the
  full test roster table (every test file, module docstring, test name) from the live collectible
  suite. Idempotent; safe to run without a prior pytest run since it only needs to collect, not execute.
- ``python -m utils.generate_test_results_rst`` -- rewrites ``docs/source/qa/test_results.rst``
  from the latest ``junit.xml``; this is the one QA page with actual pass/fail numbers rather than
  just what exists. **Requires a prior pytest run** -- exits with a clear message if ``junit.xml``
  is not yet present.

Run both after every pytest run that should update the published docs, then rebuild Sphinx
(see the full pipeline in section 6 above).

8. Manual verification checklist
--------------------------------------

A lightweight "did the environment actually come up correctly" pass, distinct from
:doc:`../operations`'s deeper experiment-running walkthrough:

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - Check
     - Expected result
   * - ``curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/``
     - ``200`` -- landing page
   * - ``curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs``
     - ``200`` -- Swagger UI
   * - ``curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/redoc``
     - ``200`` -- ReDoc
   * - ``ollama list``
     - At least one model shown
   * - Run one tiny experiment via ``/experiments`` (1 student, 1 archetype, ``max_tokens`` ~40)
     - Progress bar completes; :doc:`../operations`'s Scenario 1, step 4-7
   * - ``cd docs/source && make html``
     - Clean build, warning count matches the stable baseline noted in this wiki's own pages
   * - ``python utils/serve_docs.py``
     - Opens the built docs over real HTTP; search results show context snippets, not just titles
       (a ``file://``-only open cannot do this -- see :mod:`utils.serve_docs`'s own docstring)

For a full, real end-to-end walkthrough beyond this smoke-check level -- filling in the experiment
form, watching live SSE progress, reading results through every page, then the same thing again via
raw ``curl`` against the API, then inspecting the resulting JSONL/SQLite directly -- see
:doc:`../operations` in full.

9. Quick reference
------------------------

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Task
     - Command
   * - Start everything needed for the web UI
     - ``ollama serve`` (separate terminal), then ``uvicorn api.app:app --reload``
   * - Run the full test suite (no E2E)
     - ``pytest tests --ignore=tests/e2e -v``
   * - Run E2E only
     - ``pytest tests/e2e -v``
   * - Full suite + coverage + Allure + HTML report (Windows)
     - ``tox -e py312``
   * - Full suite + coverage + Allure + HTML report (Ubuntu)
     - ``tox -e linux-full``
   * - Lint + type-check + format check
     - ``tox -e lint``
   * - Apply black formatting
     - ``tox -e format``
   * - Requirement-traceability gate
     - ``tox -e traceability``
   * - Tests + traceability + Sphinx docs in one call (Windows)
     - ``tox -e full``
   * - Build docs only
     - ``tox -e docs`` or ``sphinx-build docs/source docs/source/_build/html``
   * - Tests + regenerate QA RST + build docs (verified Windows pipeline, section 6)
     - ``pytest ... tests --ignore=tests/e2e -v; python -m utils.generate_qa_roster; python -m utils.generate_test_results_rst; sphinx-build docs/source docs/source/_build/html``
   * - Serve docs with working search
     - ``python utils/serve_docs.py``
   * - Regenerate a dependency lock file
     - ``pip-compile requirements.in --output-file=requirements-base.txt``
   * - Copy a run's JSONL data into SQLite
     - http://127.0.0.1:8000/db_export (pick a run, click **Send to DB**, or check several rows and
       click **Send selected to DB**) -- or ``python -m cli.manage export-db <run_id>`` from a
       terminal with no server running at all; see :doc:`../operations`
   * - Ops without the web UI up
     - ``python -m cli.manage {serve, status, list-runs, export-db}`` -- see :mod:`cli.manage`
