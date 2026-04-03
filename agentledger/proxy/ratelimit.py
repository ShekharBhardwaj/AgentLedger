"""
Proxy-level rate limiting for LLM calls.

Limits are requests-per-minute (RPM), applied independently per dimension.
All limits are optional — only configured ones are enforced.

    AGENTLEDGER_RATE_LIMIT_RPM          Global limit across all calls
    AGENTLEDGER_RATE_LIMIT_SESSION_RPM  Per session_id
    AGENTLEDGER_RATE_LIMIT_AGENT_RPM    Per agent_name
    AGENTLEDGER_RATE_LIMIT_USER_RPM     Per user_id

When a limit is exceeded the proxy returns HTTP 429 with a JSON error body.
The agent receives it like any other upstream error — no special handling needed.

Uses a sliding window (60-second window, in-memory). Single-process safe.
No Redis or external state required.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimitConfig:
    global_rpm:  Optional[int] = None
    session_rpm: Optional[int] = None
    agent_rpm:   Optional[int] = None
    user_rpm:    Optional[int] = None

    @property
    def enabled(self) -> bool:
        return any([self.global_rpm, self.session_rpm, self.agent_rpm, self.user_rpm])


class RateLimiter:

    def __init__(self, config: RateLimitConfig) -> None:
        self._config = config
        self._windows: dict[str, deque] = defaultdict(deque)

    def check(
        self,
        session_id: Optional[str],
        agent_name: Optional[str],
        user_id:    Optional[str],
    ) -> Optional[str]:
        """
        Returns an error message string if any limit is exceeded, else None.
        Records this request against all applicable windows on success.
        """
        if not self._config.enabled:
            return None

        now = time.monotonic()

        checks = []
        if self._config.global_rpm:
            checks.append(("global",  "__global__",           self._config.global_rpm))
        if self._config.session_rpm and session_id:
            checks.append(("session", f"session:{session_id}", self._config.session_rpm))
        if self._config.agent_rpm and agent_name:
            checks.append(("agent",   f"agent:{agent_name}",   self._config.agent_rpm))
        if self._config.user_rpm and user_id:
            checks.append(("user",    f"user:{user_id}",       self._config.user_rpm))

        # Check all windows before recording — don't partially record then reject
        for label, key, limit in checks:
            window = self._windows[key]
            _evict(window, now)
            if len(window) >= limit:
                return (
                    f"Rate limit exceeded: {limit} requests/min per {label}. "
                    f"Current: {len(window)}. Retry after 60 seconds."
                )

        # All checks passed — record this request in every window
        for _, key, _ in checks:
            self._windows[key].append(now)

        return None


def _evict(window: deque, now: float) -> None:
    """Remove timestamps older than 60 seconds from the sliding window."""
    while window and now - window[0] > 60:
        window.popleft()
