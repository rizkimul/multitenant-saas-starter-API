from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import RateLimitError
from app.core.rate_limit import _workspace_rate_limit


def make_settings(*, requests: int = 60, window: int = 60) -> MagicMock:
    s = MagicMock()
    s.rate_limit_requests = requests
    s.rate_limit_window_seconds = window
    return s


def make_redis(*, incr_return: int = 1) -> AsyncMock:
    r = AsyncMock()
    r.incr.return_value = incr_return
    r.expire.return_value = True
    return r


class TestWorkspaceRateLimit:
    async def test_allows_request_under_limit(self) -> None:
        redis = make_redis(incr_return=1)
        settings = make_settings(requests=60)

        await _workspace_rate_limit(slug="acme", redis=redis, settings=settings)

        redis.incr.assert_called_once()

    async def test_raises_when_limit_exceeded(self) -> None:
        redis = make_redis(incr_return=61)
        settings = make_settings(requests=60)

        with pytest.raises(RateLimitError):
            await _workspace_rate_limit(slug="acme", redis=redis, settings=settings)

    async def test_allows_exactly_at_limit(self) -> None:
        redis = make_redis(incr_return=60)
        settings = make_settings(requests=60)

        await _workspace_rate_limit(slug="acme", redis=redis, settings=settings)

    async def test_sets_expire_on_first_increment(self) -> None:
        redis = make_redis(incr_return=1)
        settings = make_settings(requests=60, window=60)

        await _workspace_rate_limit(slug="acme", redis=redis, settings=settings)

        redis.expire.assert_called_once()
        _, ttl_arg = redis.expire.call_args.args
        assert ttl_arg == 60

    async def test_skips_expire_on_subsequent_increments(self) -> None:
        redis = make_redis(incr_return=5)
        settings = make_settings(requests=60)

        await _workspace_rate_limit(slug="acme", redis=redis, settings=settings)

        redis.expire.assert_not_called()

    async def test_key_includes_slug(self) -> None:
        redis = make_redis(incr_return=1)
        settings = make_settings()

        await _workspace_rate_limit(slug="my-workspace", redis=redis, settings=settings)

        key_used: str = redis.incr.call_args.args[0]
        assert "my-workspace" in key_used

    async def test_different_slugs_use_different_keys(self) -> None:
        settings = make_settings()

        redis_a = make_redis(incr_return=1)
        redis_b = make_redis(incr_return=1)

        with patch("app.core.rate_limit.time") as mock_time:
            mock_time.time.return_value = 1_000_000.0

            await _workspace_rate_limit(
                slug="workspace-a", redis=redis_a, settings=settings
            )
            await _workspace_rate_limit(
                slug="workspace-b", redis=redis_b, settings=settings
            )

        key_a: str = redis_a.incr.call_args.args[0]
        key_b: str = redis_b.incr.call_args.args[0]
        assert key_a != key_b

    async def test_key_format_is_correct(self) -> None:
        redis = make_redis(incr_return=1)
        settings = make_settings(window=60)

        with patch("app.core.rate_limit.time") as mock_time:
            mock_time.time.return_value = 1_000_000.0
            expected_bucket = 1_000_000 // 60

            await _workspace_rate_limit(slug="acme", redis=redis, settings=settings)

        key_used: str = redis.incr.call_args.args[0]
        assert key_used == f"rl:acme:{expected_bucket}"
