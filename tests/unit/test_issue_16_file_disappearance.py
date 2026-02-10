"""Regression tests for GitHub issue #16: Files intermittently missing.

These tests describe the CORRECT (fixed) behavior. They FAIL against the
current buggy code. Once the fixes are applied, all tests should pass.

Two root causes:
1. Silent file mounting failures — _mount_files() should raise when requested
   files cannot be mounted, not silently skip them.
2. Directories stored as files — the generated file detection pipeline should
   filter out directories at every layer.
"""

import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.models import (
    CodeExecution,
    ExecRequest,
    ExecutionOutput,
    ExecutionStatus,
    FileRef,
    OutputType,
)
from src.models.exec import RequestFile
from src.models.files import FileInfo
from src.services.orchestrator import ExecutionContext, ExecutionOrchestrator

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_service():
    service = MagicMock()
    service.get_session = AsyncMock()
    service.create_session = AsyncMock()
    service.list_sessions_by_entity = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_file_service():
    service = MagicMock()
    service.get_file_info = AsyncMock(return_value=None)
    service.list_files = AsyncMock(return_value=[])
    service.get_file_content = AsyncMock(return_value=b"real file content")
    service.store_execution_output_file = AsyncMock(return_value="generated-file-id")
    return service


@pytest.fixture
def mock_execution_service():
    service = MagicMock()
    service.execute_code = AsyncMock()
    return service


@pytest.fixture
def mock_state_service():
    service = MagicMock()
    service.get_state = AsyncMock(return_value=None)
    return service


@pytest.fixture
def orchestrator(mock_session_service, mock_file_service, mock_execution_service, mock_state_service):
    return ExecutionOrchestrator(
        session_service=mock_session_service,
        file_service=mock_file_service,
        execution_service=mock_execution_service,
        state_service=mock_state_service,
    )


@pytest.fixture
def sidecar_app(tmp_path):
    """Load the real sidecar FastAPI app with WORKING_DIR set to tmp_path.

    Uses importlib because docker/sidecar/main.py is a standalone file (not a
    Python package) and the 'docker' directory name conflicts with the installed
    docker-py package.
    """
    old_wd = os.environ.get("WORKING_DIR")
    os.environ["WORKING_DIR"] = str(tmp_path)
    try:
        sidecar_path = Path(__file__).resolve().parent.parent.parent / "docker" / "sidecar" / "main.py"
        spec = importlib.util.spec_from_file_location("sidecar_main", str(sidecar_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod.app
    finally:
        if old_wd is None:
            os.environ.pop("WORKING_DIR", None)
        else:
            os.environ["WORKING_DIR"] = old_wd


def _make_file_info(file_id="file-abc", filename="data.xlsm"):
    return FileInfo(
        file_id=file_id,
        filename=filename,
        size=1024,
        content_type="application/octet-stream",
        created_at=datetime.now(),
        path=f"/mnt/data/{filename}",
    )


# ===========================================================================
# Issue 1 — Silent file mounting failures
# ===========================================================================


class TestFileMountingFailuresRaiseErrors:
    """_mount_files should raise when requested files cannot be mounted,
    rather than silently skipping them and proceeding with execution."""

    @pytest.mark.asyncio
    async def test_mount_raises_when_file_info_not_found(self, orchestrator, mock_file_service):
        """Should raise when a requested file's metadata cannot be found
        in Redis (neither by ID nor by name fallback)."""
        mock_file_service.get_file_info.return_value = None
        mock_file_service.list_files.return_value = []

        request_file = RequestFile(id="file-abc", session_id="sess-1", name="data.xlsm")
        request = ExecRequest(code="open('data.xlsm')", lang="python", files=[request_file])
        ctx = ExecutionContext(request=request, request_id="req-1")

        with pytest.raises(Exception):
            await orchestrator._mount_files(ctx)

    @pytest.mark.asyncio
    async def test_mount_raises_when_file_content_unavailable(self, orchestrator, mock_file_service):
        """Should raise when a requested file's content cannot be fetched
        from MinIO, even if metadata was found."""
        mock_file_service.get_file_info.return_value = _make_file_info()
        mock_file_service.get_file_content.return_value = None

        request_file = RequestFile(id="file-abc", session_id="sess-1", name="data.xlsm")
        request = ExecRequest(code="open('data.xlsm')", lang="python", files=[request_file])
        ctx = ExecutionContext(request=request, request_id="req-1")

        with pytest.raises(Exception):
            await orchestrator._mount_files(ctx)

    @pytest.mark.asyncio
    async def test_mount_raises_when_all_files_fail(self, orchestrator, mock_file_service):
        """Should raise when all requested files fail to mount, not return
        an empty list indistinguishable from 'no files requested'."""
        mock_file_service.get_file_info.return_value = None
        mock_file_service.list_files.return_value = []

        files = [RequestFile(id=f"file-{i}", session_id="sess-1", name=f"f{i}.csv") for i in range(3)]
        request = ExecRequest(code="print(1)", lang="python", files=files)
        ctx = ExecutionContext(request=request, request_id="req-1")

        with pytest.raises(Exception):
            await orchestrator._mount_files(ctx)

    @pytest.mark.asyncio
    async def test_mount_raises_on_partial_failure(self, orchestrator, mock_file_service):
        """Should raise when any requested file fails to mount, even if
        other files succeed."""
        good_info = _make_file_info(file_id="good-1", filename="good.csv")

        # First file succeeds, second file's metadata is missing
        mock_file_service.get_file_info.side_effect = [good_info, None]
        mock_file_service.list_files.return_value = []
        mock_file_service.get_file_content.return_value = b"csv data"

        files = [
            RequestFile(id="good-1", session_id="sess-1", name="good.csv"),
            RequestFile(id="bad-1", session_id="sess-1", name="missing.csv"),
        ]
        request = ExecRequest(code="print(1)", lang="python", files=files)
        ctx = ExecutionContext(request=request, request_id="req-1")

        with pytest.raises(Exception):
            await orchestrator._mount_files(ctx)


# ===========================================================================
# Issue 2 — Directories stored as files
# ===========================================================================


class TestDirectoriesFilteredFromGeneratedFiles:
    """The generated file detection pipeline should filter out directories
    at every layer, preventing them from being stored as files in MinIO."""

    @pytest.mark.asyncio
    async def test_detect_generated_files_excludes_directories(self):
        """_detect_generated_files should not include directory entries
        returned by the sidecar's GET /files endpoint."""
        from src.services.execution.runner import CodeExecutionRunner

        runner = CodeExecutionRunner(kubernetes_manager=MagicMock())

        handle = MagicMock(
            pod_ip="10.0.0.1",
            sidecar_url="http://10.0.0.1:8080",
            name="test-pod",
        )

        # Sidecar returns a directory ("xl") alongside a regular file.
        # The directory has size=0 because the sidecar sets size=0 for non-files.
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "files": [
                {"name": "code.py", "size": 50},
                {"name": "xl", "size": 0, "is_file": False},
                {"name": "output.png", "size": 5000},
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = await runner._detect_generated_files(handle)

        names = [Path(f["path"]).name for f in result]
        assert "xl" not in names, "Directories should be filtered out of generated files"
        assert "output.png" in names

    @pytest.mark.asyncio
    async def test_sidecar_list_files_excludes_directories(self, tmp_path, sidecar_app):
        """The sidecar's GET /files endpoint should only list regular files,
        not directories."""
        (tmp_path / "output.png").write_bytes(b"\x89PNG")
        (tmp_path / "xl").mkdir()
        (tmp_path / "xl" / "vbaProject.bin").write_bytes(b"\x00" * 100)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=sidecar_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/files")

        assert response.status_code == 200
        file_names = [f["name"] for f in response.json()["files"]]

        assert "xl" not in file_names, "Directories should not appear in file listing"
        assert "output.png" in file_names

    @pytest.mark.asyncio
    async def test_sidecar_download_rejects_directory_path(self, tmp_path, sidecar_app):
        """The sidecar's GET /files/{path} endpoint should return an error
        status for directory paths, not a 200 with a JSON directory listing."""
        (tmp_path / "xl").mkdir()
        (tmp_path / "xl" / "vbaProject.bin").write_bytes(b"\x00" * 100)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=sidecar_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/files/xl")

        assert response.status_code == 400, f"Expected 400 for directory path, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_copy_file_from_pod_rejects_json_directory_listing(self):
        """copy_file_from_pod should return None when the sidecar responds
        with a JSON directory listing instead of file content."""
        # Simulate the sidecar returning a JSON directory listing for a directory
        dir_listing = {"files": [{"name": "vbaProject.bin", "path": "xl/vbaProject.bin", "size": 100}]}
        json_bytes = json.dumps(dir_listing).encode()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = json_bytes
        mock_response.headers = {"content-type": "application/json"}

        handle = MagicMock(
            pod_ip="10.0.0.1",
            sidecar_url="http://10.0.0.1:8080",
            name="test-pod",
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            from src.services.kubernetes.manager import KubernetesManager

            manager = KubernetesManager.__new__(KubernetesManager)
            content = await manager.copy_file_from_pod(handle, "xl")

        assert content is None, "Should return None for JSON directory listings, not store them as file content"

    @pytest.mark.asyncio
    async def test_handle_generated_files_does_not_store_directories(
        self, orchestrator, mock_file_service, mock_execution_service
    ):
        """_handle_generated_files should not store directory entries in MinIO.
        When _get_file_from_container returns None for a directory, the entry
        should be skipped entirely."""
        mock_execution = CodeExecution(
            execution_id="exec-1",
            session_id="sess-1",
            code="import zipfile; zipfile.ZipFile('data.xlsm').extractall('/mnt/data')",
            status=ExecutionStatus.COMPLETED,
            exit_code=0,
            execution_time_ms=100,
            outputs=[
                ExecutionOutput(type=OutputType.FILE, content="/mnt/data/xl"),
            ],
        )

        # After the fix, _get_file_from_container should return None for
        # directories (since copy_file_from_pod rejects JSON listings)
        with patch.object(orchestrator, "_get_file_from_container", return_value=None):
            request = ExecRequest(code="extract()", lang="python")
            ctx = ExecutionContext(
                request=request,
                request_id="req-1",
                session_id="sess-1",
                execution=mock_execution,
                container=MagicMock(),
            )

            generated = await orchestrator._handle_generated_files(ctx)

        mock_file_service.store_execution_output_file.assert_not_called()
        assert generated == [], "No files should be stored for directory entries"
