"""
Tests for Idempotency implementation in Worker.
Validates content hash deduplication and Redis integration.
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.worker import (
    compute_content_hash,
    get_redis_client,
    is_content_processed,
    mark_content_processed,
)


class TestContentHashing:
    """Test suite for content hash computation."""

    def test_compute_content_hash_deterministic(self):
        """Content hash should be deterministic for same input."""
        content = "This is a test document chunk"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters

    def test_compute_content_hash_different_content(self):
        """Different content should produce different hashes."""
        content1 = "Document chunk 1"
        content2 = "Document chunk 2"

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)

        assert hash1 != hash2

    def test_compute_content_hash_empty_string(self):
        """Empty string should produce valid hash."""
        content = ""
        hash_result = compute_content_hash(content)

        assert len(hash_result) == 64
        # SHA-256 of empty string
        expected = hashlib.sha256(b"").hexdigest()
        assert hash_result == expected

    def test_compute_content_hash_unicode(self):
        """Unicode content should be handled correctly."""
        content = "Documento con caracteres especiales: ñ, á, é, í, ó, ú, ü"
        hash_result = compute_content_hash(content)

        assert len(hash_result) == 64
        # Should be deterministic
        assert hash_result == compute_content_hash(content)

    def test_compute_content_hash_large_content(self):
        """Large content should be hashed efficiently."""
        content = "x" * 1_000_000  # 1MB of data
        hash_result = compute_content_hash(content)

        assert len(hash_result) == 64


class TestRedisIdempotency:
    """Test suite for Redis-based idempotency tracking."""

    @pytest.mark.asyncio
    async def test_is_content_processed_new_content(self):
        """New content should return False."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            result = await is_content_processed("test_hash_123")

            assert result is False
            mock_redis.exists.assert_called_once_with("processed:test_hash_123")

    @pytest.mark.asyncio
    async def test_is_content_processed_duplicate_content(self):
        """Duplicate content should return True."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            result = await is_content_processed("test_hash_456")

            assert result is True
            mock_redis.exists.assert_called_once_with("processed:test_hash_456")

    @pytest.mark.asyncio
    async def test_is_content_processed_redis_failure(self):
        """Redis failure should fail-open (allow processing)."""
        mock_redis = AsyncMock()
        mock_redis.exists.side_effect = Exception("Redis connection failed")

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            result = await is_content_processed("test_hash_789")

            # Should fail-open: allow processing to continue
            assert result is False

    @pytest.mark.asyncio
    async def test_mark_content_processed_success(self):
        """Marking content as processed should set Redis key with TTL."""
        mock_redis = AsyncMock()

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            await mark_content_processed("test_hash_abc", ttl=3600)

            mock_redis.setex.assert_called_once_with(
                "processed:test_hash_abc", 3600, "1"
            )

    @pytest.mark.asyncio
    async def test_mark_content_processed_default_ttl(self):
        """Default TTL should be 24 hours (86400 seconds)."""
        mock_redis = AsyncMock()

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            await mark_content_processed("test_hash_def")

            mock_redis.setex.assert_called_once_with(
                "processed:test_hash_def", 86400, "1"
            )

    @pytest.mark.asyncio
    async def test_mark_content_processed_redis_failure(self):
        """Redis failure when marking should not crash (non-critical)."""
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = Exception("Redis write failed")

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            # Should not raise exception
            await mark_content_processed("test_hash_ghi")


class TestIdempotencyIntegration:
    """Integration tests for idempotency in worker flow."""

    @pytest.mark.asyncio
    async def test_duplicate_detection_workflow(self):
        """Complete workflow: hash -> check -> process -> mark."""
        content = "Test document for processing"
        content_hash = compute_content_hash(content)

        mock_redis = AsyncMock()
        # First check: not processed
        mock_redis.exists.return_value = 0

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            # Check if processed
            is_duplicate = await is_content_processed(content_hash)
            assert is_duplicate is False

            # Simulate processing...

            # Mark as processed
            await mark_content_processed(content_hash)

            # Verify Redis calls
            assert mock_redis.exists.called
            assert mock_redis.setex.called

    @pytest.mark.asyncio
    async def test_duplicate_content_skipped(self):
        """Duplicate content should be skipped in processing."""
        content = "Duplicate document"
        content_hash = compute_content_hash(content)

        mock_redis = AsyncMock()
        # Simulate already processed
        mock_redis.exists.return_value = 1

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            is_duplicate = await is_content_processed(content_hash)

            assert is_duplicate is True
            # Processing should be skipped

    @pytest.mark.asyncio
    async def test_redis_client_singleton(self):
        """Redis client should be reused (singleton pattern)."""
        # Reset global client
        import core.worker

        core.worker.redis_client = None

        mock_redis = MagicMock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            client1 = await get_redis_client()
            client2 = await get_redis_client()

            # Should return same instance
            assert client1 is client2


class TestIdempotencyEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_duplicate_checks(self):
        """Multiple concurrent checks for same hash should be handled."""
        content_hash = "concurrent_test_hash"
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            # Simulate concurrent checks
            results = await asyncio.gather(
                is_content_processed(content_hash),
                is_content_processed(content_hash),
                is_content_processed(content_hash),
            )

            # All should return False (not processed)
            assert all(r is False for r in results)

    @pytest.mark.asyncio
    async def test_hash_collision_extremely_unlikely(self):
        """SHA-256 collision should be astronomically unlikely."""
        # Generate many different contents
        hashes = set()
        for i in range(10000):
            content = f"Document number {i} with unique content"
            hash_result = compute_content_hash(content)
            hashes.add(hash_result)

        # All hashes should be unique
        assert len(hashes) == 10000

    @pytest.mark.asyncio
    async def test_ttl_expiration_allows_reprocessing(self):
        """After TTL expiration, content should be reprocessable."""
        content_hash = "expired_hash"
        mock_redis = AsyncMock()

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            # Mark as processed with short TTL
            await mark_content_processed(content_hash, ttl=1)

            # Simulate TTL expiration (Redis returns 0 for expired keys)
            mock_redis.exists.return_value = 0

            # Should be reprocessable
            is_duplicate = await is_content_processed(content_hash)
            assert is_duplicate is False

    def test_content_hash_case_sensitive(self):
        """Content hash should be case-sensitive."""
        content1 = "Test Content"
        content2 = "test content"

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)

        assert hash1 != hash2

    def test_content_hash_whitespace_sensitive(self):
        """Content hash should be sensitive to whitespace."""
        content1 = "Test Content"
        content2 = "Test  Content"  # Extra space

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)

        assert hash1 != hash2


class TestIdempotencyPerformance:
    """Performance and scalability tests."""

    def test_hash_computation_performance(self):
        """Hash computation should be fast."""
        import time

        content = "x" * 100_000  # 100KB

        start = time.time()
        for _ in range(100):
            compute_content_hash(content)
        elapsed = time.time() - start

        # Should complete 100 hashes in reasonable time
        assert elapsed < 1.0  # Less than 1 second

    @pytest.mark.asyncio
    async def test_redis_operations_async(self):
        """Redis operations should be truly async."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0

        with patch("core.worker.get_redis_client", return_value=mock_redis):
            # Multiple concurrent operations
            tasks = [is_content_processed(f"hash_{i}") for i in range(100)]

            results = await asyncio.gather(*tasks)

            # All should complete successfully
            assert len(results) == 100
            assert all(r is False for r in results)


# Import asyncio for concurrent tests
import asyncio

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
