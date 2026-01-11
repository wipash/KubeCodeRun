"""Unit tests for the cleanup scheduler service."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.events import ExecutionCompleted, SessionDeleted, event_bus
from src.services.cleanup import CleanupScheduler, cleanup_scheduler


@pytest.fixture
def cleanup_service():
    """Create a cleanup scheduler for testing."""
    scheduler = CleanupScheduler(delay_seconds=1)
    yield scheduler
    # Cleanup after test
    scheduler.stop()


@pytest.fixture
def mock_file_service():
    """Create mock file service."""
    service = AsyncMock()
    service.cleanup_session_files = AsyncMock()
    return service


@pytest.fixture
def mock_execution_service():
    """Create mock execution service."""
    return AsyncMock()


@pytest.fixture
def mock_state_archival_service():
    """Create mock state archival service."""
    service = AsyncMock()
    service.archive_inactive_states = AsyncMock(return_value={"archived": 0, "failed": 0})
    service.cleanup_expired_archives = AsyncMock(return_value={"deleted": 0})
    return service


class TestCleanupSchedulerInit:
    """Tests for CleanupScheduler initialization."""

    def test_init_default_delay(self):
        """Test default delay seconds."""
        scheduler = CleanupScheduler()
        assert scheduler.delay_seconds == 5

    def test_init_custom_delay(self):
        """Test custom delay seconds."""
        scheduler = CleanupScheduler(delay_seconds=10)
        assert scheduler.delay_seconds == 10

    def test_init_empty_state(self):
        """Test initial state is empty."""
        scheduler = CleanupScheduler()
        assert scheduler._pending_cleanups == {}
        assert scheduler._cleaned_sessions == set()
        assert scheduler._execution_service is None
        assert scheduler._file_service is None
        assert scheduler._state_archival_service is None
        assert scheduler._archival_task is None
        assert scheduler._started is False


class TestCleanupSchedulerServices:
    """Tests for service configuration."""

    def test_set_services(
        self, cleanup_service, mock_execution_service, mock_file_service, mock_state_archival_service
    ):
        """Test setting services."""
        cleanup_service.set_services(
            mock_execution_service,
            mock_file_service,
            mock_state_archival_service,
        )

        assert cleanup_service._execution_service == mock_execution_service
        assert cleanup_service._file_service == mock_file_service
        assert cleanup_service._state_archival_service == mock_state_archival_service

    def test_set_services_without_archival(self, cleanup_service, mock_execution_service, mock_file_service):
        """Test setting services without archival service."""
        cleanup_service.set_services(mock_execution_service, mock_file_service)

        assert cleanup_service._execution_service == mock_execution_service
        assert cleanup_service._file_service == mock_file_service
        assert cleanup_service._state_archival_service is None

    def test_set_kubernetes_manager(self, cleanup_service):
        """Test setting Kubernetes manager."""
        mock_manager = MagicMock()
        cleanup_service.set_kubernetes_manager(mock_manager)
        # Just logs, no state change expected


class TestCleanupSchedulerLifecycle:
    """Tests for start/stop lifecycle."""

    def test_start_registers_handlers(self, cleanup_service):
        """Test that start registers event handlers."""
        cleanup_service.start()

        assert cleanup_service._started is True

    def test_start_twice_is_idempotent(self, cleanup_service):
        """Test that calling start twice doesn't re-register handlers."""
        cleanup_service.start()
        cleanup_service.start()

        assert cleanup_service._started is True

    def test_stop_unregisters_handlers(self, cleanup_service):
        """Test that stop unregisters event handlers."""
        cleanup_service.start()
        cleanup_service.stop()

        assert cleanup_service._started is False

    def test_stop_twice_is_idempotent(self, cleanup_service):
        """Test that calling stop twice is safe."""
        cleanup_service.start()
        cleanup_service.stop()
        cleanup_service.stop()

        assert cleanup_service._started is False

    def test_stop_without_start(self, cleanup_service):
        """Test that stop without start is safe."""
        cleanup_service.stop()
        assert cleanup_service._started is False

    @pytest.mark.asyncio
    async def test_stop_clears_pending_cleanups(self, cleanup_service):
        """Test that stop clears pending cleanups."""
        cleanup_service.start()
        # Add a pending cleanup task (use a mock instead of real task)
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        cleanup_service._pending_cleanups["test-session"] = mock_task

        cleanup_service.stop()

        assert cleanup_service._pending_cleanups == {}
        mock_task.cancel.assert_called_once()

    def test_stop_clears_cleaned_sessions(self, cleanup_service):
        """Test that stop clears cleaned sessions."""
        cleanup_service.start()
        cleanup_service._cleaned_sessions.add("session1")
        cleanup_service._cleaned_sessions.add("session2")

        cleanup_service.stop()

        assert cleanup_service._cleaned_sessions == set()

    @pytest.mark.asyncio
    async def test_start_with_archival_enabled(self, cleanup_service, mock_state_archival_service):
        """Test that start creates archival task when enabled."""
        cleanup_service.set_services(None, None, mock_state_archival_service)

        with patch("src.services.cleanup.settings") as mock_settings:
            mock_settings.state_archive_enabled = True
            mock_settings.state_archive_check_interval_seconds = 60

            cleanup_service.start()

            assert cleanup_service._archival_task is not None
            assert not cleanup_service._archival_task.done()

            cleanup_service.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_archival_task(self, cleanup_service, mock_state_archival_service):
        """Test that stop cancels archival task."""
        cleanup_service.set_services(None, None, mock_state_archival_service)

        with patch("src.services.cleanup.settings") as mock_settings:
            mock_settings.state_archive_enabled = True
            mock_settings.state_archive_check_interval_seconds = 60

            cleanup_service.start()
            archival_task = cleanup_service._archival_task

            cleanup_service.stop()

            # Wait briefly for task cancellation to complete
            await asyncio.sleep(0.01)

            assert cleanup_service._archival_task is None
            assert archival_task.cancelled() or archival_task.done()


class TestEventHandling:
    """Tests for event handling."""

    @pytest.mark.asyncio
    async def test_on_execution_completed(self, cleanup_service):
        """Test handling of execution completed event."""
        cleanup_service.start()

        event = ExecutionCompleted(
            execution_id="exec-123",
            session_id="session-456",
            success=True,
        )

        # Should not raise, just logs
        await cleanup_service._on_execution_completed(event)

    @pytest.mark.asyncio
    async def test_on_session_deleted_cleans_files(self, cleanup_service, mock_file_service):
        """Test that session deleted event triggers file cleanup."""
        cleanup_service.set_services(None, mock_file_service)
        cleanup_service.start()

        event = SessionDeleted(session_id="session-123")

        await cleanup_service._on_session_deleted(event)

        mock_file_service.cleanup_session_files.assert_called_once_with("session-123")

    @pytest.mark.asyncio
    async def test_on_session_deleted_cancels_pending_cleanup(self, cleanup_service, mock_file_service):
        """Test that session deleted cancels pending cleanup."""
        cleanup_service.set_services(None, mock_file_service)
        cleanup_service.start()

        # Add a pending cleanup
        cleanup_service._pending_cleanups["session-123"] = asyncio.create_task(asyncio.sleep(100))

        event = SessionDeleted(session_id="session-123")
        await cleanup_service._on_session_deleted(event)

        assert "session-123" not in cleanup_service._pending_cleanups
        assert "session-123" in cleanup_service._cleaned_sessions

    @pytest.mark.asyncio
    async def test_on_session_deleted_limits_cleaned_set(self, cleanup_service, mock_file_service):
        """Test that cleaned sessions set is limited to 1000."""
        cleanup_service.set_services(None, mock_file_service)
        cleanup_service.start()

        # Add 1001 sessions to cleaned set (already over limit)
        for i in range(1001):
            cleanup_service._cleaned_sessions.add(f"session-{i}")

        event = SessionDeleted(session_id="new-session")
        await cleanup_service._on_session_deleted(event)

        # The code adds session_id first, then checks if > 1000 and clears
        # So after adding "new-session" (making 1002), it clears the whole set
        assert len(cleanup_service._cleaned_sessions) == 0

    @pytest.mark.asyncio
    async def test_on_session_deleted_handles_cleanup_error(self, cleanup_service, mock_file_service):
        """Test graceful handling of file cleanup errors."""
        mock_file_service.cleanup_session_files.side_effect = Exception("Storage error")
        cleanup_service.set_services(None, mock_file_service)
        cleanup_service.start()

        event = SessionDeleted(session_id="session-123")

        # Should not raise
        await cleanup_service._on_session_deleted(event)

    @pytest.mark.asyncio
    async def test_on_session_deleted_without_file_service(self, cleanup_service):
        """Test session deleted without file service configured."""
        cleanup_service.start()

        event = SessionDeleted(session_id="session-123")

        # Should not raise
        await cleanup_service._on_session_deleted(event)


class TestScheduleCleanup:
    """Tests for manual cleanup scheduling."""

    @pytest.mark.asyncio
    async def test_schedule_cleanup_default_delay(self, cleanup_service):
        """Test manual cleanup scheduling with default delay."""
        cleanup_service.start()

        with patch.object(cleanup_service, "_on_execution_completed", new_callable=AsyncMock) as mock_handler:
            cleanup_service.schedule_cleanup("session-123")

            # Wait for task to execute
            await asyncio.sleep(0.1)

            mock_handler.assert_called_once()
            call_args = mock_handler.call_args[0][0]
            assert call_args.session_id == "session-123"
            assert call_args.execution_id == "manual"

    @pytest.mark.asyncio
    async def test_schedule_cleanup_custom_delay(self, cleanup_service):
        """Test manual cleanup scheduling with custom delay."""
        cleanup_service.start()

        # Just verify it doesn't raise
        cleanup_service.schedule_cleanup("session-123", delay_seconds=2)


class TestPendingCount:
    """Tests for pending count property."""

    def test_pending_count_empty(self, cleanup_service):
        """Test pending count when empty."""
        assert cleanup_service.pending_count == 0

    def test_pending_count_with_tasks(self, cleanup_service):
        """Test pending count with tasks."""
        cleanup_service._pending_cleanups["session1"] = MagicMock()
        cleanup_service._pending_cleanups["session2"] = MagicMock()

        assert cleanup_service.pending_count == 2


class TestArchivalLoop:
    """Tests for the archival background loop."""

    @pytest.mark.asyncio
    async def test_archival_loop_basic(self, cleanup_service, mock_state_archival_service):
        """Test basic archival loop execution."""
        cleanup_service.set_services(None, None, mock_state_archival_service)

        with patch("src.services.cleanup.settings") as mock_settings:
            mock_settings.state_archive_check_interval_seconds = 0.1

            # Start the loop
            task = asyncio.create_task(cleanup_service._archival_loop())

            # Wait a bit for the loop to run
            await asyncio.sleep(0.3)

            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Archival should have been called
            assert mock_state_archival_service.archive_inactive_states.call_count >= 1

    @pytest.mark.asyncio
    async def test_archival_loop_handles_no_service(self, cleanup_service):
        """Test archival loop when no service is configured."""
        with patch("src.services.cleanup.settings") as mock_settings:
            mock_settings.state_archive_check_interval_seconds = 0.05

            task = asyncio.create_task(cleanup_service._archival_loop())

            await asyncio.sleep(0.15)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_archival_loop_handles_error(self, cleanup_service, mock_state_archival_service):
        """Test archival loop handles errors gracefully."""
        mock_state_archival_service.archive_inactive_states.side_effect = Exception("Database error")
        cleanup_service.set_services(None, None, mock_state_archival_service)

        with patch("src.services.cleanup.settings") as mock_settings:
            mock_settings.state_archive_check_interval_seconds = 0.05

            task = asyncio.create_task(cleanup_service._archival_loop())

            await asyncio.sleep(0.15)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_archival_loop_cleanup_counter(self, cleanup_service, mock_state_archival_service):
        """Test archival loop cleanup counter logic."""
        cleanup_service.set_services(None, None, mock_state_archival_service)

        with patch("src.services.cleanup.settings") as mock_settings:
            mock_settings.state_archive_check_interval_seconds = 0.01

            # Run the loop for enough iterations to trigger cleanup
            cleanup_service._archival_cleanup_counter = 5

            task = asyncio.create_task(cleanup_service._archival_loop())

            await asyncio.sleep(0.05)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Cleanup should have been called when counter reached 6
            mock_state_archival_service.cleanup_expired_archives.assert_called()


class TestGlobalInstance:
    """Tests for the global cleanup_scheduler instance."""

    def test_global_instance_exists(self):
        """Test that global instance exists."""
        assert cleanup_scheduler is not None
        assert isinstance(cleanup_scheduler, CleanupScheduler)

    def test_global_instance_default_delay(self):
        """Test global instance has correct default delay."""
        assert cleanup_scheduler.delay_seconds == 5
