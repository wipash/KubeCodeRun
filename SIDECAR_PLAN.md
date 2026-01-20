# Implementation Plan: Fold Sidecar into Main Codebase

## Overview

Move `docker/sidecar/` into `src/sidecar/` and refactor to use `src/config/languages.py` as the true single source of truth for language execution.

**Why:** The sidecar is not a generic microservice; it's an intrinsic component of KubeCodeRun. Its `get_language_command()` function is the operational realization of the language configuration. Keeping them separate creates sync bugs and violates the "single source of truth" principle that `languages.py` claims to provide.

**Current problem:**
- `src/config/languages.py` defines `execution_command` but it's **never used**
- `docker/sidecar/main.py` reimplements all execution logic in a hardcoded `if/elif` chain
- The two files have different commands, filenames, and execution patterns

---

## Phase 1: Extend LanguageConfig for Sidecar Needs

**File:** `src/config/languages.py`

The current `LanguageConfig` has `execution_command` that's unused. Replace it with fields the sidecar actually needs:

```python
@dataclass(frozen=True)
class LanguageConfig:
    code: str
    name: str
    image: str
    user_id: int
    file_extension: str
    timeout_multiplier: float = 1.0
    memory_multiplier: float = 1.0
    environment: dict[str, str] = field(default_factory=dict)

    # NEW: Sidecar execution fields
    code_filename: str = ""             # e.g., "code.py", "main.go", "Code.java"
    compile_command: str | None = None  # e.g., "rustc {file} -o /tmp/code"
    run_command: str = ""               # e.g., "python {file}", "/tmp/code"
```

**Key decisions:**
- Remove `execution_command` and `uses_stdin` (dead code)
- Add `code_filename` - where sidecar writes code
- Add `compile_command` (optional) - for compiled languages
- Add `run_command` - how to execute (post-compilation if applicable)
- Use `{file}` and `{workdir}` as template placeholders

**Example configurations:**

```python
"py": LanguageConfig(
    code="py",
    name="Python",
    image="python:latest",
    user_id=65532,
    file_extension="py",
    code_filename="code.py",
    compile_command=None,
    run_command="python {file}",
),
"rs": LanguageConfig(
    code="rs",
    name="Rust",
    image="rust:latest",
    user_id=65532,
    file_extension="rs",
    code_filename="main.rs",
    compile_command="rustc {file} -o /tmp/main",
    run_command="/tmp/main",
),
"ts": LanguageConfig(
    code="ts",
    name="TypeScript",
    image="nodejs:latest",
    user_id=65532,
    file_extension="ts",
    code_filename="code.ts",
    compile_command=None,
    run_command="node /opt/scripts/ts-runner.js {file}",
),
```

---

## Phase 2: Move Sidecar Files

**Directory changes:**

```
# Before
docker/sidecar/
├── Dockerfile
├── main.py
├── requirements.txt
└── .dockerignore

# After
src/sidecar/
├── Dockerfile
├── main.py
├── requirements.txt
└── .dockerignore

docker/sidecar/  # Remove entirely
```

**Commands:**

```bash
mkdir -p src/sidecar
mv docker/sidecar/main.py src/sidecar/
mv docker/sidecar/requirements.txt src/sidecar/
mv docker/sidecar/Dockerfile src/sidecar/
mv docker/sidecar/.dockerignore src/sidecar/
rmdir docker/sidecar
```

---

## Phase 3: Update Sidecar Dockerfile

**File:** `src/sidecar/Dockerfile`

The build context changes from `docker/sidecar/` to project root. Key changes:

```dockerfile
# Before
COPY main.py .
COPY requirements.txt .

# After - build context is now project root
COPY src/sidecar/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python -r /tmp/requirements.txt

# Copy only what sidecar needs from src/
COPY src/sidecar/main.py /app/
COPY src/config/languages.py /app/
```

**Build command changes:**

```bash
# Before
docker build -t sidecar docker/sidecar/

# After
docker build -f src/sidecar/Dockerfile -t sidecar .
```

---

## Phase 4: Refactor Sidecar main.py

**File:** `src/sidecar/main.py`

Replace the hardcoded `get_language_command()` function with config-driven logic:

```python
# NEW import (works locally AND in container)
try:
    from languages import LANGUAGES, LanguageConfig  # In container
except ImportError:
    from src.config.languages import LANGUAGES, LanguageConfig  # Local dev

def get_language_command(
    language: str, code: str, working_dir: str, container_env: dict[str, str]
) -> tuple[list[str], Path | None]:
    """Get execution command from LanguageConfig."""

    # Normalize language code
    lang_code = language.lower()
    if lang_code == "python":
        lang_code = "py"
    elif lang_code == "javascript":
        lang_code = "js"
    # ... other aliases

    config = LANGUAGES.get(lang_code)
    if not config:
        return [], None

    # Write code to file
    code_file = Path(working_dir) / config.code_filename
    code_file.write_text(code)

    # Build environment wrapper
    env = container_env or {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp"}
    env_args = [f"{k}={v}" for k, v in env.items()]

    # Template substitution
    file_str = str(code_file)
    safe_wd = shlex.quote(working_dir)

    if config.compile_command:
        # Compiled language: sh -c "compile && run"
        compile_cmd = config.compile_command.format(file=file_str, workdir=safe_wd)
        run_cmd = config.run_command.format(file=file_str, workdir=safe_wd)
        full_cmd = f"cd {safe_wd} && {compile_cmd} && {run_cmd}"
        return ["/usr/bin/env", "-i"] + env_args + ["sh", "-c", full_cmd], code_file
    else:
        # Interpreted language: direct execution
        run_parts = config.run_command.format(file=file_str, workdir=safe_wd).split()
        return ["/usr/bin/env", "-i"] + env_args + run_parts, code_file
```

**Delete:** The entire 50-line `if/elif` chain currently in `get_language_command()`.

---

## Phase 5: Update Build Scripts & CI

**Files to update:**

### justfile (if it has sidecar build targets)

```makefile
# Before
sidecar-build:
    docker build -t sidecar docker/sidecar/

# After
sidecar-build:
    docker build -f src/sidecar/Dockerfile -t sidecar .
```

### CI/CD pipelines (GitHub Actions, etc.)

- Update any references to `docker/sidecar/`
- Update build context for sidecar image

### Helm chart (if it references dockerfile path)

- Check `helm-deployments/kubecoderun/` for any hardcoded paths

---

## Phase 6: Handle Local Development

**Problem:** When developing locally, `from languages import ...` won't work because the file isn't copied yet.

**Solution 1: Conditional import pattern** (shown in Phase 4)

```python
try:
    from languages import LANGUAGES  # In container
except ImportError:
    from src.config.languages import LANGUAGES  # Local dev
```

**Solution 2: Symlink for local IDE support**

```bash
# Optional: Create symlink for local IDE support
cd src/sidecar
ln -s ../config/languages.py languages.py
echo "languages.py" >> .gitignore  # Don't commit the symlink
```

**Solution 3: Proper Python packaging**

Add to `src/sidecar/pyproject.toml`:

```toml
[project]
name = "kubecoderun-sidecar"
dependencies = ["fastapi", "pydantic", "uvicorn"]

[tool.setuptools.package-data]
"*" = ["*.py"]
```

Then for local dev: `pip install -e src/sidecar`

The conditional import (Solution 1) is the simplest and recommended approach.

---

## Phase 7: Testing

### Unit tests for new LanguageConfig fields

```python
def test_all_languages_have_sidecar_config():
    for code, config in LANGUAGES.items():
        assert config.code_filename, f"{code} missing code_filename"
        assert config.run_command, f"{code} missing run_command"
```

### Integration test for command generation

```python
def test_get_language_command_python():
    cmd, file = get_language_command("py", "print('hi')", "/mnt/data", {})
    assert "python" in cmd
    assert file.name == "code.py"
```

### Build verification

```bash
# Verify sidecar builds correctly
docker build -f src/sidecar/Dockerfile -t test-sidecar .
docker run --rm test-sidecar python -c "from languages import LANGUAGES; print(len(LANGUAGES))"
```

---

## Migration Checklist

- [ ] Extend `LanguageConfig` with `code_filename`, `compile_command`, `run_command`
- [ ] Update all 12 language configs with new fields
- [ ] Remove dead fields (`execution_command`, `uses_stdin`) and their helper functions
- [ ] Move `docker/sidecar/*` to `src/sidecar/`
- [ ] Update `src/sidecar/Dockerfile` for new build context
- [ ] Refactor `get_language_command()` to use `LanguageConfig`
- [ ] Update `justfile` / build scripts
- [ ] Update CI/CD pipelines
- [ ] Add unit tests for new config fields
- [ ] Test sidecar build and execution
- [ ] Update `AGENTS.md` / docs if they reference old paths

---

## Risk Mitigation

1. **Rollback plan:** Keep `docker/sidecar/` as a git branch until verified in staging
2. **Feature flag:** Could add env var `USE_CONFIG_COMMANDS=true` in sidecar to toggle between old/new logic during transition
3. **Staged rollout:** Deploy to one language pool first (e.g., Python) before all languages

---

## Benefits After Migration

1. **True single source of truth** - Language config lives in one place
2. **IDE support** - Jump-to-definition, autocomplete, type checking all work
3. **Refactoring safety** - Change `LanguageConfig` and IDE shows where sidecar needs updates
4. **Shared types** - Can share Pydantic models between main app and sidecar
5. **Unified testing** - Can test command generation in main test suite
6. **No sync bugs** - Impossible for sidecar and config to drift apart
