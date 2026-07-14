from __future__ import annotations

import asyncio
import hashlib
import multiprocessing
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .config import settings
from .normalization import normalize_characters, unicode_range
from .observability import logger
from .registry import FontSpec
from .subsetter import OPTIONS_VERSION, build_subset_worker


class ServiceBusyError(RuntimeError):
    pass


class CacheCapacityError(RuntimeError):
    pass


class GenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SubsetResult:
    key: str
    path: Path
    characters: int
    unicode_range: str
    cached: bool


class SubsetService:
    def __init__(self) -> None:
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        self._context = multiprocessing.get_context("spawn")
        self._generation_slots = asyncio.Semaphore(settings.generation_workers)
        self._inflight: dict[str, asyncio.Task[SubsetResult]] = {}
        self._processes: set[multiprocessing.Process] = set()
        self._guard = asyncio.Lock()
        self._cache_guard = threading.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._closed = False

    def normalize_and_validate(self, value: str) -> str:
        characters = normalize_characters(value)
        if not characters.strip():
            raise ValueError("no printable characters")
        if len(characters) > settings.max_characters:
            raise ValueError(f"too many unique characters; maximum is {settings.max_characters}")
        return characters

    def key_for(self, font: FontSpec, characters: str) -> str:
        payload = "\n".join((font.id, font.version, OPTIONS_VERSION, characters))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def path_for(self, font: FontSpec, key: str) -> Path:
        directory = settings.cache_dir / font.id / font.version
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{key}.woff2"

    async def resolve(self, font: FontSpec, raw_characters: str) -> SubsetResult:
        if self._closed:
            raise ServiceBusyError("font generation service is shutting down")

        characters = self.normalize_and_validate(raw_characters)
        key = self.key_for(font, characters)
        destination = self.path_for(font, key)
        if destination.is_file():
            self.record_access(destination)
            result = self._result(key, destination, characters, True)
            self._log_result(font, result, 0.0)
            return result

        loop = asyncio.get_running_loop()
        async with self._guard:
            task = self._inflight.get(key)
            if task is None:
                if len(self._inflight) >= settings.max_pending_generations:
                    raise ServiceBusyError("too many pending font generations")
                task = loop.create_task(
                    self._generate_logged(font, key, characters, destination),
                    name=f"font-subset-{key[:12]}",
                )
                self._inflight[key] = task
                task.add_done_callback(
                    lambda completed, subset_key=key: self._generation_done(
                        loop, subset_key, completed
                    )
                )

        return await asyncio.shield(task)

    async def start(self) -> None:
        self._closed = False
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(), name="font-cache-cleanup"
            )

    def readiness(self) -> tuple[bool, str]:
        if self._closed:
            return False, "service is shutting down"
        try:
            settings.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=settings.cache_dir, prefix=".ready-", delete=True):
                pass
        except OSError:
            return False, "cache directory is not writable"
        return True, "ready"

    async def close(self) -> None:
        self._closed = True
        cleanup_task = self._cleanup_task
        self._cleanup_task = None
        if cleanup_task is not None:
            cleanup_task.cancel()
            await asyncio.gather(cleanup_task, return_exceptions=True)

        tasks = tuple(self._inflight.values())
        if tasks:
            for task in tasks:
                task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=settings.shutdown_timeout,
                )
            except TimeoutError:
                for task in tasks:
                    task.cancel()

        processes = tuple(self._processes)
        for process in processes:
            if process.is_alive():
                process.terminate()

        deadline = time.monotonic() + settings.shutdown_timeout
        while any(process.is_alive() for process in processes) and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        for process in processes:
            if process.is_alive():
                process.kill()

    def _generation_done(
        self,
        loop: asyncio.AbstractEventLoop,
        key: str,
        task: asyncio.Task[SubsetResult],
    ) -> None:
        if not task.cancelled():
            task.exception()
        if not loop.is_closed():
            loop.create_task(self._remove_inflight(key, task))

    async def _remove_inflight(self, key: str, task: asyncio.Task[SubsetResult]) -> None:
        async with self._guard:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)

    async def _generate_logged(
        self, font: FontSpec, key: str, characters: str, destination: Path
    ) -> SubsetResult:
        started = time.monotonic()
        try:
            result = await self._generate(font, key, characters, destination)
        except BaseException as error:
            logger.error(
                "font subset generation failed",
                extra={
                    "event": "subset_generation_failed",
                    "font_id": font.id,
                    "character_count": len(characters),
                    "subset_hash": key,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "error_type": type(error).__name__,
                },
            )
            raise
        self._log_result(font, result, time.monotonic() - started)
        return result

    async def _generate(
        self, font: FontSpec, key: str, characters: str, destination: Path
    ) -> SubsetResult:
        lock_path = destination.with_suffix(".lock")
        deadline = time.monotonic() + settings.generation_timeout
        owns_lock = False

        while not destination.is_file():
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
                finally:
                    os.close(descriptor)
                owns_lock = True
                break
            except FileExistsError:
                try:
                    lock_age = time.time() - lock_path.stat().st_mtime
                    if lock_age > settings.generation_timeout * 2:
                        lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out waiting for font generation lock")
                await asyncio.sleep(0.05)

        if destination.is_file():
            self.record_access(destination)
            return self._result(key, destination, characters, True)

        acquired_slot = False
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for font generation capacity")
            await asyncio.wait_for(self._generation_slots.acquire(), timeout=remaining)
            acquired_slot = True

            await asyncio.to_thread(self._ensure_cache_capacity, font.path.stat().st_size)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("font generation timed out")
            await self._run_process(font.path, characters, destination, remaining)
            self.record_access(destination)
            return self._result(key, destination, characters, False)
        finally:
            if acquired_slot:
                self._generation_slots.release()
            if owns_lock:
                lock_path.unlink(missing_ok=True)

    async def _run_process(
        self, source: Path, characters: str, destination: Path, timeout: float
    ) -> int:
        receiver, sender = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=build_subset_worker,
            args=(str(source), characters, str(destination), sender),
            name=f"font-subsetter-{destination.stem[:12]}",
        )
        deadline = time.monotonic() + timeout
        try:
            process.start()
            sender.close()
            self._processes.add(process)
            while process.is_alive() and time.monotonic() < deadline:
                await asyncio.sleep(0.05)

            if process.is_alive():
                process.terminate()
                termination_deadline = time.monotonic() + 2
                while process.is_alive() and time.monotonic() < termination_deadline:
                    await asyncio.sleep(0.05)
                if process.is_alive():
                    process.kill()
                process.join(timeout=1)
                raise TimeoutError("font generation timed out")

            process.join(timeout=0)
            if not receiver.poll():
                raise GenerationError(f"font worker exited with code {process.exitcode}")
            succeeded, size, error_type = receiver.recv()
            if not succeeded:
                raise GenerationError(f"font worker failed: {error_type}")
            return int(size)
        finally:
            self._processes.discard(process)
            receiver.close()
            sender.close()
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            if process.pid is not None:
                temporary_path = destination.with_suffix(
                    destination.suffix + f".{process.pid}.tmp"
                )
                temporary_path.unlink(missing_ok=True)
                if not process.is_alive():
                    process.close()

    @staticmethod
    def _ensure_cache_capacity(reserve_bytes: int) -> None:
        usage = shutil.disk_usage(settings.cache_dir)
        if usage.free - reserve_bytes < settings.min_free_bytes:
            raise CacheCapacityError("insufficient free space for font cache")

        cache_bytes = 0
        for path in settings.cache_dir.rglob("*.woff2"):
            try:
                cache_bytes += path.stat().st_size
            except FileNotFoundError:
                continue
        if cache_bytes + reserve_bytes > settings.max_cache_bytes:
            raise CacheCapacityError("font cache capacity limit reached")

    @staticmethod
    def _access_path(path: Path) -> Path:
        return path.with_suffix(path.suffix + ".access")

    def record_access(self, path: Path) -> None:
        with self._cache_guard:
            if path.is_file():
                self._access_path(path).touch(exist_ok=True)

    def cleanup_stale_cache(self, now: float | None = None) -> int:
        cutoff = (time.time() if now is None else now) - (
            settings.cache_max_age_days * 86400
        )
        deleted = 0
        reclaimed_bytes = 0

        for path in settings.cache_dir.rglob("*.woff2"):
            if not path.is_file():
                continue
            with self._cache_guard:
                try:
                    access_path = self._access_path(path)
                    try:
                        last_access = access_path.stat().st_mtime
                    except FileNotFoundError:
                        last_access = path.stat().st_mtime
                    if last_access >= cutoff or path.with_suffix(".lock").exists():
                        continue
                    size = path.stat().st_size
                    path.unlink()
                    access_path.unlink(missing_ok=True)
                except FileNotFoundError:
                    continue
                except OSError as error:
                    logger.warning(
                        "stale font cache entry could not be deleted",
                        extra={
                            "event": "font_cache_cleanup_failed",
                            "error_type": type(error).__name__,
                        },
                    )
                    continue
            deleted += 1
            reclaimed_bytes += size
            self._remove_empty_cache_directories(path.parent)

        for access_path in settings.cache_dir.rglob("*.woff2.access"):
            if not access_path.with_suffix("").exists():
                access_path.unlink(missing_ok=True)

        logger.info(
            "font cache cleanup completed",
            extra={
                "event": "font_cache_cleanup_completed",
                "deleted_entries": deleted,
                "reclaimed_bytes": reclaimed_bytes,
            },
        )
        return deleted

    @staticmethod
    def _remove_empty_cache_directories(directory: Path) -> None:
        while directory != settings.cache_dir:
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent

    async def _cleanup_loop(self) -> None:
        while not self._closed:
            try:
                await asyncio.to_thread(self.cleanup_stale_cache)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.exception(
                    "font cache cleanup failed",
                    extra={
                        "event": "font_cache_cleanup_failed",
                        "error_type": type(error).__name__,
                    },
                )
            await asyncio.sleep(settings.cache_cleanup_interval)

    @staticmethod
    def _result(key: str, path: Path, characters: str, cached: bool) -> SubsetResult:
        return SubsetResult(key, path, len(characters), unicode_range(characters), cached)

    @staticmethod
    def _log_result(font: FontSpec, result: SubsetResult, duration: float) -> None:
        logger.info(
            "font subset resolved",
            extra={
                "event": "subset_resolved",
                "font_id": font.id,
                "character_count": result.characters,
                "subset_hash": result.key,
                "cache_hit": result.cached,
                "output_bytes": result.path.stat().st_size,
                "duration_ms": round(duration * 1000, 2),
            },
        )


subset_service = SubsetService()
