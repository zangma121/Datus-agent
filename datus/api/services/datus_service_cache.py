"""Global LRU cache: (tenant_id, project_id) -> DatusService.

Uses Future-based thundering herd prevention — concurrent requests for
the same (tenant_id, project_id) share a single factory call. Tenant-level
keying (datus-agent-cube M1b) gives each tenant its own DatusService and
AgentConfig clone; the default (empty) tenant preserves the legacy
project-only behavior.
"""

import asyncio
import collections
from typing import Awaitable, Callable, Optional

from datus.api.services.datus_service import DatusService
from datus.utils.loggings import get_logger

logger = get_logger(__name__)


class DatusServiceCache:
    """Async LRU cache for DatusService instances."""

    def __init__(self, max_size: int = 128):
        self._max_size = max_size
        self._cache: collections.OrderedDict[tuple, DatusService] = collections.OrderedDict()
        self._futures: dict[str, asyncio.Future[DatusService]] = {}
        self._lock = asyncio.Lock()
        self._pending_tasks: set[asyncio.Task] = set()

    def _track(self, task: asyncio.Task) -> asyncio.Task:
        """Register a background task so drain()/shutdown() can await it."""
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
        return task

    async def get_or_create(
        self,
        project_id: str,
        factory: Callable[[], Awaitable[DatusService]],
        expected_fingerprint: Optional[str] = None,
        tenant_id: str = "",
    ) -> DatusService:
        """Return cached DatusService or create via factory (thundering-herd safe).

        Entries are keyed on ``(tenant_id, project_id)``; ``tenant_id="")``
        is the default tenant and behaves like the legacy project-only key.

        If ``expected_fingerprint`` is provided and does not match the cached
        instance's ``config_fingerprint``, the stale entry is evicted before
        creating a new one.
        """
        cache_key = (str(tenant_id or ""), project_id)
        is_creator = False
        stale_svc: Optional[DatusService] = None

        async with self._lock:
            # Fast path: cache hit
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if expected_fingerprint is None or cached.config_fingerprint == expected_fingerprint:
                    self._cache.move_to_end(cache_key)
                    return cached
                # Fingerprint mismatch. Rebuilding now would orphan any in-flight
                # chat task: its interaction broker lives in this instance's
                # task_manager, so a later /chat/user_interaction answer would
                # hit a fresh, empty manager and fail with "No active task found
                # for this session". Defer the config swap while the instance is
                # busy — keep serving it until its tasks drain, after which the
                # next request rebuilds with the new config.
                if cached.has_active_tasks():
                    self._cache.move_to_end(cache_key)
                    logger.info(
                        f"Deferring DatusService rebuild for {cache_key}: "
                        f"AgentConfig fingerprint changed but tasks are still active"
                    )
                    return cached
                # Idle instance — safe to evict and rebuild with the new config.
                stale_svc = self._cache.pop(cache_key)
                logger.info(f"Evicting DatusService for {cache_key} due to AgentConfig fingerprint mismatch")

            # Another coroutine is already creating this entry — share its future
            if cache_key in self._futures:
                fut = self._futures[cache_key]
            else:
                # We are the creator — register a future for waiters
                fut = asyncio.get_running_loop().create_future()
                self._futures[cache_key] = fut
                is_creator = True

        if stale_svc is not None:
            await self._dispose(cache_key, stale_svc)

        if not is_creator:
            # Wait for the creator coroutine to finish
            return await fut

        # We are the creator — run the factory outside the lock
        try:
            svc = await factory()
        except Exception as e:
            async with self._lock:
                self._futures.pop(project_id, None)
            if not fut.done():
                fut.set_exception(e)
            raise

        async with self._lock:
            self._cache[cache_key] = svc
            self._cache.move_to_end(cache_key)
            self._futures.pop(cache_key, None)

            # Evict oldest if over capacity, but skip services with active tasks
            evicted = []
            while len(self._cache) > self._max_size:
                # Find the oldest entry without active tasks
                candidate_key = None
                for key in self._cache:
                    if key == cache_key:
                        continue
                    if not self._cache[key].has_active_tasks():
                        candidate_key = key
                        break
                if candidate_key is None:
                    break  # all entries have active tasks — allow cache to exceed max_size
                old_svc = self._cache.pop(candidate_key)
                evicted.append((candidate_key, old_svc))

        # Resolve the future so waiters get the result
        if not fut.done():
            fut.set_result(svc)

        # Shutdown evicted services outside the lock
        for old_pid, old_svc in evicted:
            logger.info(f"LRU evicting DatusService for project {old_pid}")
            self._track(asyncio.create_task(old_svc.shutdown()))

        return svc

    async def evict(self, project_id: str, tenant_id: str = "") -> None:
        """Evict a DatusService from cache (config change).

        Always removes from cache so new requests get fresh config.
        If the service has active tasks, defers shutdown until tasks drain.
        """
        cache_key = (str(tenant_id or ""), project_id)
        async with self._lock:
            svc = self._cache.pop(cache_key, None)
        if not svc:
            return
        await self._dispose(cache_key, svc)

    async def _dispose(self, project_id: str, svc: DatusService) -> None:
        """Shutdown a service, deferring if it still has active tasks."""
        if svc.has_active_tasks():
            logger.info(f"Evicting DatusService for project {project_id} (deferring shutdown — active tasks)")
            self._track(asyncio.create_task(self._deferred_shutdown(project_id, svc)))
        else:
            logger.info(f"Evicting DatusService for project {project_id}")
            await svc.shutdown()

    @staticmethod
    async def _deferred_shutdown(project_id: str, svc: DatusService) -> None:
        """Wait for active tasks to drain, then shutdown."""
        try:
            await svc.task_manager.wait_all_tasks()
            await svc.shutdown()
            logger.info(f"Deferred shutdown completed for project {project_id}")
        except Exception:
            logger.exception(f"Error in deferred shutdown for project {project_id}")

    async def drain(self) -> None:
        """Await all pending background shutdown tasks before the loop closes."""
        if self._pending_tasks:
            results = await asyncio.gather(*list(self._pending_tasks), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    logger.warning("Background shutdown task failed", exc_info=result)

    async def shutdown(self) -> None:
        """Shutdown all cached DatusService instances (application exit)."""
        await self.drain()
        async with self._lock:
            items = list(self._cache.items())
            self._cache.clear()
        for pid, svc in items:
            try:
                await svc.shutdown()
            except Exception:
                logger.exception(f"Error shutting down DatusService for project {pid}")
        logger.info("DatusServiceCache shut down")
