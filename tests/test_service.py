import asyncio
import os
import time
from dataclasses import replace

import pytest

import app.service as service_module
from app.config import settings
from app.registry import FONTS
from app.service import CacheCapacityError, ServiceBusyError, SubsetService


def write_cache_entry(path, accessed_at, *, marker=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"wOF2-test")
    os.utime(path, (accessed_at, accessed_at))
    if marker:
        access_path = path.with_suffix(path.suffix + ".access")
        access_path.touch()
        os.utime(access_path, (accessed_at, accessed_at))


@pytest.mark.asyncio
async def test_generation_timeout_terminates_worker_and_cleans_files(tmp_path, monkeypatch):
    test_settings = replace(
        settings,
        cache_dir=tmp_path,
        generation_timeout=0.01,
        min_free_bytes=1,
    )
    monkeypatch.setattr(service_module, "settings", test_settings)
    service = SubsetService()
    font = FONTS["zen-kaku-regular"]
    destination = tmp_path / "timeout.woff2"

    with pytest.raises(TimeoutError):
        await service._generate(font, "a" * 64, "日本語ABC", destination)

    assert not destination.exists()
    assert not destination.with_suffix(".lock").exists()
    assert not list(tmp_path.glob("*.tmp"))
    assert not service._processes


def test_cache_capacity_rejects_new_generation(tmp_path, monkeypatch):
    test_settings = replace(
        settings,
        cache_dir=tmp_path,
        max_cache_bytes=1,
        min_free_bytes=1,
    )
    monkeypatch.setattr(service_module, "settings", test_settings)

    with pytest.raises(CacheCapacityError, match="capacity limit"):
        SubsetService._ensure_cache_capacity(2)


def test_cache_cleanup_deletes_entries_not_accessed_for_30_days(tmp_path, monkeypatch):
    test_settings = replace(
        settings,
        cache_dir=tmp_path,
        cache_max_age_days=30,
        min_free_bytes=1,
    )
    monkeypatch.setattr(service_module, "settings", test_settings)
    service = SubsetService()
    now = time.time()
    directory = tmp_path / "zen-kaku-regular" / "v1"
    stale = directory / f"{'a' * 64}.woff2"
    legacy_stale = directory / f"{'b' * 64}.woff2"
    fresh = directory / f"{'c' * 64}.woff2"
    boundary = directory / f"{'d' * 64}.woff2"

    write_cache_entry(stale, now - 31 * 86400)
    write_cache_entry(legacy_stale, now - 31 * 86400, marker=False)
    write_cache_entry(fresh, now - 29 * 86400)
    write_cache_entry(boundary, now - 30 * 86400)

    assert service.cleanup_stale_cache(now) == 2
    assert not stale.exists()
    assert not stale.with_suffix(".woff2.access").exists()
    assert not legacy_stale.exists()
    assert fresh.exists()
    assert boundary.exists()


def test_cache_cleanup_skips_entry_with_generation_lock(tmp_path, monkeypatch):
    test_settings = replace(settings, cache_dir=tmp_path, cache_max_age_days=30)
    monkeypatch.setattr(service_module, "settings", test_settings)
    service = SubsetService()
    now = time.time()
    path = tmp_path / "font" / "v1" / f"{'a' * 64}.woff2"
    write_cache_entry(path, now - 31 * 86400)
    path.with_suffix(".lock").touch()

    assert service.cleanup_stale_cache(now) == 0
    assert path.exists()


def test_record_access_refreshes_cache_marker(tmp_path, monkeypatch):
    test_settings = replace(settings, cache_dir=tmp_path)
    monkeypatch.setattr(service_module, "settings", test_settings)
    service = SubsetService()
    path = tmp_path / "font" / "v1" / f"{'a' * 64}.woff2"
    old_access = time.time() - 31 * 86400
    write_cache_entry(path, old_access)

    service.record_access(path)

    assert path.with_suffix(".woff2.access").stat().st_mtime > old_access


@pytest.mark.asyncio
async def test_cache_cleanup_starts_with_service(tmp_path, monkeypatch):
    test_settings = replace(
        settings,
        cache_dir=tmp_path,
        cache_cleanup_interval=0.01,
    )
    monkeypatch.setattr(service_module, "settings", test_settings)
    service = SubsetService()
    calls = 0

    def cleanup():
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr(service, "cleanup_stale_cache", cleanup)
    await service.start()
    await asyncio.sleep(0.03)
    await service.close()

    assert calls >= 1


@pytest.mark.asyncio
async def test_identical_requests_share_one_generation(tmp_path, monkeypatch):
    test_settings = replace(settings, cache_dir=tmp_path, min_free_bytes=1)
    monkeypatch.setattr(service_module, "settings", test_settings)
    service = SubsetService()
    font = FONTS["zen-kaku-regular"]
    calls = 0

    async def fake_generation(font, key, characters, destination):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        destination.write_bytes(b"wOF2-test")
        return service._result(key, destination, characters, False)

    monkeypatch.setattr(service, "_generate_logged", fake_generation)
    first, second = await asyncio.gather(
        service.resolve(font, "BA"),
        service.resolve(font, "AB"),
    )

    assert calls == 1
    assert first.key == second.key
    await service.close()


@pytest.mark.asyncio
async def test_generation_queue_has_a_hard_limit(tmp_path, monkeypatch):
    test_settings = replace(
        settings,
        cache_dir=tmp_path,
        generation_workers=1,
        max_pending_generations=1,
        min_free_bytes=1,
    )
    monkeypatch.setattr(service_module, "settings", test_settings)
    service = SubsetService()
    font = FONTS["zen-kaku-regular"]
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_generation(font, key, characters, destination):
        started.set()
        await release.wait()
        destination.write_bytes(b"wOF2-test")
        return service._result(key, destination, characters, False)

    monkeypatch.setattr(service, "_generate_logged", blocked_generation)
    first = asyncio.create_task(service.resolve(font, "first"))
    await started.wait()
    with pytest.raises(ServiceBusyError, match="too many pending"):
        await service.resolve(font, "second")
    release.set()
    await first
    await service.close()
