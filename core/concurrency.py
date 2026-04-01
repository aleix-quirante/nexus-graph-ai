import asyncio
import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio.lock import Lock

logger = logging.getLogger(__name__)


class OntologyLockManager:
    """
    Distributed lock manager for ontology operations.
    Ensures safe concurrent access to nodes and relationships
    across the distributed system using Redis.
    """

    def __init__(self, redis_url: str):
        self.redis: redis.Redis = redis.from_url(redis_url, decode_responses=True)

    @asynccontextmanager
    async def acquire_edge_locks(
        self, source_id: str, target_id: str
    ) -> AsyncGenerator[int, None]:
        """
        Acquires distributed locks for a pair of node IDs to safely mutate edges.
        Locks are acquired strictly at the Node ID level.
        Lexicographically sorts source_id and target_id to mathematically prevent deadlocks.
        Employs defensive TTLs to prevent orphaned locks.
        """
        if source_id == target_id:
            raise ValueError(
                "source_id and target_id must be different to acquire edge locks."
            )

        # Lexicographical sort to mathematically prevent deadlocks in high concurrency
        sorted_ids = sorted([source_id, target_id])
        lock1_name = f"node_lock:{sorted_ids[0]}"
        lock2_name = f"node_lock:{sorted_ids[1]}"

        # Defensive TTL of 10 seconds to prevent orphaned locks
        lock1 = self.redis.lock(name=lock1_name, timeout=10, blocking_timeout=5)
        lock2 = self.redis.lock(name=lock2_name, timeout=10, blocking_timeout=5)

        acquired_lock1 = False
        acquired_lock2 = False

        try:
            acquired_lock1 = await lock1.acquire()
            if not acquired_lock1:
                raise TimeoutError(f"Failed to acquire lock for node {sorted_ids[0]}")

            acquired_lock2 = await lock2.acquire()
            if not acquired_lock2:
                raise TimeoutError(f"Failed to acquire lock for node {sorted_ids[1]}")

            # Generate monotonically increasing fencing token
            fencing_token = await self.redis.incr(
                f"fencing_token:{sorted_ids[0]}:{sorted_ids[1]}"
            )

            yield fencing_token

        finally:
            if acquired_lock2:
                try:
                    await lock2.release()
                except redis.exceptions.LockError:
                    logger.warning(
                        f"Failed to release lock {lock2_name}, maybe it expired"
                    )

            if acquired_lock1:
                try:
                    await lock1.release()
                except redis.exceptions.LockError:
                    logger.warning(
                        f"Failed to release lock {lock1_name}, maybe it expired"
                    )

    async def close(self) -> None:
        """Close the Redis connection pool."""
        await self.redis.aclose()  # type: ignore
