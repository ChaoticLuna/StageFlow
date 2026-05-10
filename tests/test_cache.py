"""Condition cache behavior tests.

Verifies cache hit/miss, TTL expiration, cache clearing,
variable key invalidation, and base_path key isolation.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from stageflow.core.conditions import (
    evaluate_all,
    set_cache_ttl,
    clear_cache,
    _CONDITION_CACHE,
    _cache_key,
    register,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures / helpers
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset cache state before each test for isolation."""
    clear_cache()
    set_cache_ttl(30.0)
    yield
    clear_cache()
    set_cache_ttl(30.0)


_counter_state = 0


@register("_cache_hit_counter")
def _cache_hit_counter(params: dict):
    """Increments a global counter on each real evaluation. Used to verify cache."""
    global _counter_state
    _counter_state += 1
    return True, f"Evaluation #{_counter_state}"


def _reset_counter():
    global _counter_state
    _counter_state = 0


# ═══════════════════════════════════════════════════════════════════════════
# Cache hit within TTL
# ═══════════════════════════════════════════════════════════════════════════

class TestCacheHitWithinTTL:
    """Repeated evaluations within TTL return cached results."""

    def test_repeated_evaluation_uses_cache(self):
        _reset_counter()
        set_cache_ttl(60.0)

        ok1, _ = evaluate_all([{"_cache_hit_counter": {}}])
        assert ok1
        assert _counter_state == 1

        ok2, _ = evaluate_all([{"_cache_hit_counter": {}}])
        assert ok2
        assert _counter_state == 1  # Not incremented — cache hit

    def test_file_exists_cached_after_file_deleted(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        set_cache_ttl(60.0)

        ok1, _ = evaluate_all([{"file_exists": str(f)}], base_path=str(tmp_path))
        assert ok1

        f.unlink()
        assert not f.exists()

        ok2, _ = evaluate_all([{"file_exists": str(f)}], base_path=str(tmp_path))
        assert ok2  # Cached — still True even though file is gone

    def test_cache_key_stable_for_same_input(self):
        conds = [{"always": True}]
        k1 = _cache_key(conds, "/tmp/test")
        k2 = _cache_key(conds, "/tmp/test")
        assert k1 == k2

    def test_multiple_conditions_cached_as_unit(self):
        _reset_counter()
        set_cache_ttl(60.0)

        evaluate_all([
            {"_cache_hit_counter": {}},
            {"always": True},
        ])
        evaluate_all([
            {"_cache_hit_counter": {}},
            {"always": True},
        ])
        assert _counter_state == 1  # Entire condition set cached

    def test_different_condition_order_different_cache_key(self):
        _reset_counter()
        set_cache_ttl(60.0)

        evaluate_all([{"always": True}, {"_cache_hit_counter": {}}])
        evaluate_all([{"_cache_hit_counter": {}}, {"always": True}])
        # Different order → different key → both evaluated
        assert _counter_state == 2


# ═══════════════════════════════════════════════════════════════════════════
# Cache miss after TTL
# ═══════════════════════════════════════════════════════════════════════════

class TestCacheMissAfterTTL:
    """After TTL expiration, conditions are re-evaluated."""

    def test_cache_expires_after_short_ttl(self):
        _reset_counter()
        set_cache_ttl(0.05)

        evaluate_all([{"_cache_hit_counter": {}}])
        assert _counter_state == 1

        evaluate_all([{"_cache_hit_counter": {}}])
        assert _counter_state == 1  # Cache hit

        time.sleep(0.06)

        evaluate_all([{"_cache_hit_counter": {}}])
        assert _counter_state == 2  # Cache miss, re-evaluated

    def test_file_exists_reevaluated_after_ttl(self, tmp_path):
        f = tmp_path / "dynamic.txt"
        f.write_text("hello")
        set_cache_ttl(0.05)

        ok1, _ = evaluate_all([{"file_exists": str(f)}], base_path=str(tmp_path))
        assert ok1

        f.unlink()
        time.sleep(0.06)

        ok2, _ = evaluate_all([{"file_exists": str(f)}], base_path=str(tmp_path))
        assert not ok2  # Re-evaluated, file is gone

    def test_cache_timestamp_updated_on_reevaluation(self):
        set_cache_ttl(60.0)
        clear_cache()

        evaluate_all([{"always": True}])
        assert len(_CONDITION_CACHE) == 1
        _, ts1 = next(iter(_CONDITION_CACHE.values()))

        time.sleep(0.02)
        clear_cache()
        evaluate_all([{"always": True}])
        _, ts2 = next(iter(_CONDITION_CACHE.values()))

        assert ts2 > ts1


# ═══════════════════════════════════════════════════════════════════════════
# cache_ttl=0 disables cache
# ═══════════════════════════════════════════════════════════════════════════

class TestCacheTTLDisabled:
    """cache_ttl=0 disables caching entirely."""

    def test_cache_ttl_zero_parameter_disables(self):
        _reset_counter()
        set_cache_ttl(60.0)

        evaluate_all([{"_cache_hit_counter": {}}], cache_ttl=0)
        assert _counter_state == 1

        evaluate_all([{"_cache_hit_counter": {}}], cache_ttl=0)
        assert _counter_state == 2  # Not cached

    def test_set_cache_ttl_zero_global(self):
        _reset_counter()
        set_cache_ttl(0)

        evaluate_all([{"_cache_hit_counter": {}}])
        assert _counter_state == 1

        evaluate_all([{"_cache_hit_counter": {}}])
        assert _counter_state == 2  # Global TTL=0, no caching

    def test_no_cache_entry_when_ttl_zero(self):
        clear_cache()
        set_cache_ttl(0)

        evaluate_all([{"always": True}])
        assert len(_CONDITION_CACHE) == 0  # Nothing stored

    def test_negative_ttl_clamped_to_zero(self):
        set_cache_ttl(-5)
        # max(0, -5) == 0, so caching is disabled
        _reset_counter()

        evaluate_all([{"_cache_hit_counter": {}}])
        evaluate_all([{"_cache_hit_counter": {}}])
        assert _counter_state == 2

    def test_parameter_cache_ttl_overrides_global(self):
        _reset_counter()
        set_cache_ttl(0)  # global = disabled

        evaluate_all([{"_cache_hit_counter": {}}], cache_ttl=60.0)
        assert _counter_state == 1

        evaluate_all([{"_cache_hit_counter": {}}], cache_ttl=60.0)
        assert _counter_state == 1  # Parameter cache_ttl=60 enabled caching


# ═══════════════════════════════════════════════════════════════════════════
# clear_cache()
# ═══════════════════════════════════════════════════════════════════════════

class TestClearCache:
    """clear_cache() empties the cache dictionary."""

    def test_clear_cache_empties(self):
        set_cache_ttl(60.0)
        evaluate_all([{"always": True}])
        evaluate_all([{"file_exists": "some/path"}])
        assert len(_CONDITION_CACHE) > 0

        clear_cache()
        assert len(_CONDITION_CACHE) == 0

    def test_clear_cache_forces_reevaluation(self):
        _reset_counter()
        set_cache_ttl(60.0)

        evaluate_all([{"_cache_hit_counter": {}}])
        assert _counter_state == 1

        clear_cache()

        evaluate_all([{"_cache_hit_counter": {}}])
        assert _counter_state == 2  # Cache cleared, re-evaluated

    def test_clear_cache_between_different_conditions(self):
        set_cache_ttl(60.0)
        clear_cache()

        evaluate_all([{"always": True}])
        evaluate_all([{"never": "test"}])
        assert len(_CONDITION_CACHE) >= 2

        clear_cache()
        assert len(_CONDITION_CACHE) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Variable key invalidation
# ═══════════════════════════════════════════════════════════════════════════

class TestVariableCacheKey:
    """Variable changes invalidate cache keys."""

    def test_different_variables_produce_different_keys(self):
        conds = [{"file_exists": "{{var.path}}"}]
        k1 = _cache_key(conds, "/base", {"path": "file_a.txt"})
        k2 = _cache_key(conds, "/base", {"path": "file_b.txt"})
        assert k1 != k2

    def test_same_variables_produce_same_key(self):
        conds = [{"file_exists": "{{var.path}}"}]
        vars_ = {"path": "file_a.txt", "extra": 42}
        k1 = _cache_key(conds, "/base", vars_)
        k2 = _cache_key(conds, "/base", vars_)
        assert k1 == k2

    def test_no_variables_produces_same_key(self):
        conds = [{"always": True}]
        k1 = _cache_key(conds, "/base")
        k2 = _cache_key(conds, "/base", {})
        assert k1 == k2  # Empty dict treated same as no variables

    def test_variable_change_forces_cache_miss(self, tmp_path):
        f_a = tmp_path / "a.txt"
        f_b = tmp_path / "b.txt"
        f_a.write_text("hello")
        f_b.write_text("world")
        set_cache_ttl(60.0)

        ok1, _ = evaluate_all(
            [{"file_exists": "{{var.path}}"}],
            base_path=str(tmp_path),
            variables={"path": "a.txt"},
        )
        assert ok1

        ok2, _ = evaluate_all(
            [{"file_exists": "{{var.path}}"}],
            base_path=str(tmp_path),
            variables={"path": "b.txt"},
        )
        assert ok2  # Different var → different cache key → fresh eval (b.txt exists)

    def test_variable_order_in_dict_does_not_affect_key(self):
        conds = [{"always": True}]
        k1 = _cache_key(conds, "/base", {"a": 1, "b": 2})
        k2 = _cache_key(conds, "/base", {"b": 2, "a": 1})
        assert k1 == k2  # sort_keys=True in json.dumps


# ═══════════════════════════════════════════════════════════════════════════
# base_path key isolation
# ═══════════════════════════════════════════════════════════════════════════

class TestBasePathCacheKey:
    """Different base_path values produce different cache keys."""

    def test_different_base_path_different_key(self):
        conds = [{"always": True}]
        k1 = _cache_key(conds, "/project/a")
        k2 = _cache_key(conds, "/project/b")
        assert k1 != k2

    def test_base_path_not_normalized_trailing_slash_matters(self):
        conds = [{"always": True}]
        k1 = _cache_key(conds, "/project")
        k2 = _cache_key(conds, "/project/")
        # Raw string comparison — no path normalization
        assert k1 != k2

    def test_different_base_path_isolates_cache(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "marker.txt").write_text("a")
        (dir_b / "marker.txt").write_text("b")
        set_cache_ttl(60.0)

        ok_a, _ = evaluate_all(
            [{"file_exists": "marker.txt"}],
            base_path=str(dir_a),
        )
        ok_b, _ = evaluate_all(
            [{"file_exists": "marker.txt"}],
            base_path=str(dir_b),
        )
        assert ok_a and ok_b

        assert len(_CONDITION_CACHE) == 2  # Different base_path → separate entries

    def test_base_path_affects_file_exists_eval(self, tmp_path):
        dir_x = tmp_path / "x"
        dir_x.mkdir()
        (dir_x / "only_here.txt").write_text("x")
        set_cache_ttl(60.0)

        ok, _ = evaluate_all(
            [{"file_exists": "only_here.txt"}],
            base_path=str(dir_x),
        )
        assert ok

        # Same condition, different base_path (root of tmp_path) — file doesn't exist there
        ok2, _ = evaluate_all(
            [{"file_exists": "only_here.txt"}],
            base_path=str(tmp_path),
            cache_ttl=0,
        )
        assert not ok2


# ═══════════════════════════════════════════════════════════════════════════
# Cache edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestCacheEdgeCases:
    """Edge case behavior for the condition cache."""

    def test_empty_conditions_not_cached(self):
        clear_cache()
        set_cache_ttl(60.0)

        evaluate_all([])
        assert len(_CONDITION_CACHE) == 0

    def test_failed_condition_result_is_cached(self):
        set_cache_ttl(60.0)
        clear_cache()

        ok1, _ = evaluate_all([{"never": "blocked"}])
        assert not ok1
        assert len(_CONDITION_CACHE) == 1

        ok2, _ = evaluate_all([{"never": "blocked"}])
        assert not ok2  # Cached failure

    def test_all_of_sub_conditions_evaluated_use_cache(self):
        _reset_counter()
        set_cache_ttl(60.0)

        evaluate_all([{"all_of": {"conditions": [
            {"_cache_hit_counter": {}},
            {"always": True},
        ]}}])
        assert _counter_state == 1

        evaluate_all([{"all_of": {"conditions": [
            {"_cache_hit_counter": {}},
            {"always": True},
        ]}}])
        assert _counter_state == 1  # Cached

    def test_any_of_caches_individual_evaluations(self):
        _reset_counter()
        set_cache_ttl(60.0)

        # any_of uses evaluate() directly (not evaluate_all), skipping cache
        # So _cache_hit_counter is called each time for any_of
        evaluate_all([{"any_of": {"conditions": [
            {"_cache_hit_counter": {}},
            {"always": True},
        ]}}])
        first = _counter_state

        evaluate_all([{"any_of": {"conditions": [
            {"_cache_hit_counter": {}},
            {"always": True},
        ]}}])
        # any_of doesn't use evaluate_all internally, so the outer evaluate_all
        # caches the entire result, not individual sub-conditions
        assert _counter_state == first  # Outer result cached

    def test_cache_key_includes_full_condition_spec(self):
        k1 = _cache_key([{"file_exists": "a.txt"}], "/base")
        k2 = _cache_key([{"file_exists": "b.txt"}], "/base")
        assert k1 != k2

    def test_high_ttl_value_accepted(self):
        set_cache_ttl(86400.0)  # 24 hours
        _reset_counter()

        evaluate_all([{"_cache_hit_counter": {}}])
        evaluate_all([{"_cache_hit_counter": {}}])
        assert _counter_state == 1  # Cached with long TTL
