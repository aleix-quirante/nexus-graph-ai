from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from core.schemas import GraphExtraction

# Mock setup_telemetry before importing worker
with patch("core.observability.setup_telemetry") as mock_setup_telemetry:
    from core.worker import process_message_with_recovery


@pytest.mark.asyncio
async def test_process_message_success():
    mock_agent = AsyncMock()
    mock_agent.run.return_value.data = GraphExtraction(nodes=[], relationships=[])

    with patch("core.worker.agent", mock_agent):
        result = await process_message_with_recovery("Test content")
        assert result is not None
        mock_agent.run.assert_called_once()


@pytest.mark.asyncio
async def test_process_message_auto_recovery_success():
    mock_agent = AsyncMock()

    # Simulate validation error on first call, success on second
    mock_agent.run.side_effect = [
        ValidationError.from_exception_data("Test error", line_errors=[]),
        AsyncMock(data=GraphExtraction(nodes=[], relationships=[])),
    ]

    with patch("core.worker.agent", mock_agent):
        result = await process_message_with_recovery("Test content", max_retries=3)
        assert result is not None
        assert mock_agent.run.call_count == 2

        # Verify that error details were injected in the prompt for the retry
        call_args = mock_agent.run.call_args_list[1][0][0]
        assert "Previous extraction failed schema validation" in call_args
        assert "Test content" in call_args


@pytest.mark.asyncio
async def test_process_message_auto_recovery_failure():
    mock_agent = AsyncMock()

    # Simulate validation error always
    mock_agent.run.side_effect = ValidationError.from_exception_data(
        "Test error", line_errors=[]
    )

    with patch("core.worker.agent", mock_agent):
        with pytest.raises(ValidationError):
            await process_message_with_recovery("Test content", max_retries=2)
        assert mock_agent.run.call_count == 2
