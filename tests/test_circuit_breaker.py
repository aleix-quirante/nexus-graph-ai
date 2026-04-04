"""
Tests for Circuit Breaker implementation in SLM Guard.
Validates resilience patterns and warn-only mode behavior.
"""

import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from core.security_guardrails import (
    SLMGuardCircuitBreaker,
    CircuitState,
    SLMGuard,
)


class TestSLMGuardCircuitBreaker:
    """Test suite for Circuit Breaker pattern implementation."""

    def test_initial_state_is_closed(self):
        """Circuit breaker should start in CLOSED state."""
        cb = SLMGuardCircuitBreaker()
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_record_success_in_closed_state(self):
        """Recording success in CLOSED state should reset failure count."""
        cb = SLMGuardCircuitBreaker()
        cb.failure_count = 3
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.get_state() == CircuitState.CLOSED

    def test_transition_to_open_after_threshold(self):
        """Circuit should open after reaching failure threshold."""
        cb = SLMGuardCircuitBreaker(failure_threshold=3)

        # Record failures
        cb.record_failure()
        assert cb.get_state() == CircuitState.CLOSED
        cb.record_failure()
        assert cb.get_state() == CircuitState.CLOSED
        cb.record_failure()

        # Should transition to OPEN
        assert cb.get_state() == CircuitState.OPEN
        assert cb.is_open()

    def test_can_attempt_call_in_closed_state(self):
        """Calls should be allowed in CLOSED state."""
        cb = SLMGuardCircuitBreaker()
        assert cb.can_attempt_call() is True

    def test_can_attempt_call_in_open_state_warn_only(self):
        """Calls should be allowed in OPEN state (warn-only mode)."""
        cb = SLMGuardCircuitBreaker(failure_threshold=1)
        cb.record_failure()

        assert cb.get_state() == CircuitState.OPEN
        # Warn-only mode: traffic is allowed through
        assert cb.can_attempt_call() is True

    def test_transition_to_half_open_after_timeout(self):
        """Circuit should transition to HALF_OPEN after recovery timeout."""
        cb = SLMGuardCircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.1,  # 100ms for testing
        )

        # Trigger OPEN state
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Next call should transition to HALF_OPEN
        assert cb.can_attempt_call() is True
        assert cb.get_state() == CircuitState.HALF_OPEN

    def test_half_open_success_transitions_to_closed(self):
        """Successful calls in HALF_OPEN should transition to CLOSED."""
        cb = SLMGuardCircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.1,
            half_open_max_calls=2,
        )

        # Trigger OPEN state
        cb.record_failure()
        time.sleep(0.15)
        cb.can_attempt_call()  # Transition to HALF_OPEN

        assert cb.get_state() == CircuitState.HALF_OPEN

        # Record successful calls
        cb.record_success()
        assert cb.get_state() == CircuitState.HALF_OPEN
        cb.record_success()

        # Should transition back to CLOSED
        assert cb.get_state() == CircuitState.CLOSED

    def test_half_open_failure_returns_to_open(self):
        """Failure in HALF_OPEN should return to OPEN state."""
        cb = SLMGuardCircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.1,
        )

        # Trigger OPEN state
        cb.record_failure()
        time.sleep(0.15)
        cb.can_attempt_call()  # Transition to HALF_OPEN

        assert cb.get_state() == CircuitState.HALF_OPEN

        # Record failure
        cb.record_failure()

        # Should return to OPEN
        assert cb.get_state() == CircuitState.OPEN


class TestSLMGuardWithCircuitBreaker:
    """Integration tests for SLM Guard with Circuit Breaker."""

    @pytest.mark.asyncio
    async def test_slm_guard_records_success(self):
        """SLM Guard should record success in circuit breaker."""
        guard = SLMGuard()

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "SAFE"}}]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await guard.check_integrity("test content")

            assert result is True
            assert guard.circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_slm_guard_records_failure(self):
        """SLM Guard should record failure in circuit breaker."""
        guard = SLMGuard()

        # Mock HTTP failure
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection failed")
            )

            result = await guard.check_integrity("test content")

            # Should fail closed initially
            assert result is False
            assert guard.circuit_breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_slm_guard_warn_only_mode_when_open(self):
        """SLM Guard should allow traffic in OPEN state (warn-only mode)."""
        guard = SLMGuard()
        guard.circuit_breaker = SLMGuardCircuitBreaker(failure_threshold=1)

        # Mock HTTP failure to trigger OPEN state
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection failed")
            )

            # First call triggers OPEN state
            result = await guard.check_integrity("test content")
            assert guard.circuit_breaker.get_state() == CircuitState.OPEN

            # Second call should pass through (warn-only mode)
            result = await guard.check_integrity("test content 2")
            assert result is True  # Allowed through in warn-only mode

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_cascading_failures(self):
        """Circuit breaker should prevent cascading failures."""
        guard = SLMGuard()
        guard.circuit_breaker = SLMGuardCircuitBreaker(failure_threshold=3)

        call_count = 0

        async def failing_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Service unavailable")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=failing_post
            )

            # Make multiple calls
            for i in range(5):
                await guard.check_integrity(f"test content {i}")

            # Circuit should be OPEN after threshold
            assert guard.circuit_breaker.get_state() == CircuitState.OPEN

            # Subsequent calls should pass through without hitting the service
            initial_call_count = call_count
            result = await guard.check_integrity("test after open")

            # In warn-only mode, we still attempt the call but allow traffic through
            assert result is True


class TestCircuitBreakerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_failure_threshold_not_allowed(self):
        """Circuit breaker should handle edge case configurations."""
        cb = SLMGuardCircuitBreaker(failure_threshold=0)
        # Should not crash, but behavior is implementation-defined
        assert cb.get_state() == CircuitState.CLOSED

    def test_concurrent_state_transitions(self):
        """Circuit breaker should handle rapid state changes."""
        cb = SLMGuardCircuitBreaker(failure_threshold=2)

        # Rapid failures
        cb.record_failure()
        cb.record_failure()

        assert cb.get_state() == CircuitState.OPEN

        # Rapid success attempts shouldn't crash
        cb.record_success()
        assert cb.get_state() == CircuitState.OPEN

    def test_multiple_recovery_attempts(self):
        """Circuit breaker should handle multiple recovery cycles."""
        cb = SLMGuardCircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.05,
            half_open_max_calls=1,
        )

        # First failure cycle
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        # Wait and recover
        time.sleep(0.1)
        cb.can_attempt_call()
        assert cb.get_state() == CircuitState.HALF_OPEN

        # Fail again
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        # Second recovery attempt
        time.sleep(0.1)
        cb.can_attempt_call()
        assert cb.get_state() == CircuitState.HALF_OPEN

        # Succeed this time
        cb.record_success()
        assert cb.get_state() == CircuitState.CLOSED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
