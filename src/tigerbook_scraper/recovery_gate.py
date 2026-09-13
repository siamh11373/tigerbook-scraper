"""Drain outstanding work and probe once after a service cooldown."""

import asyncio
import time
from dataclasses import dataclass


@dataclass(eq=False)
class Lease:
    """Opaque ownership token returned by RecoveryGate.enter."""

    generation: int
    probe: bool


class RecoveryGate:
    """Shared across clients; every admitted lease must finish in a finally block."""

    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.blocked_until = 0.0
        self.recovering = False
        self.generation = 0
        self.active = set()
        self.probe = None
        self.changed = asyncio.Event()

    def _notify(self):
        self.changed.set()
        self.changed = asyncio.Event()

    def block(self, seconds):
        """Pause admissions; synchronous so a response can block before yielding."""
        self.recovering = True
        self.generation += 1
        self.blocked_until = max(self.blocked_until, self.clock() + max(0, seconds))
        self._notify()

    async def enter(self):
        """Wait for admission, returning a lease without a cancellation gap."""
        while True:
            if not self.recovering:
                lease = Lease(self.generation, False)
                self.active.add(lease)
                return lease
            delay = self.blocked_until - self.clock()
            if not self.active and self.probe is None and delay <= 0:
                lease = Lease(self.generation, True)
                self.active.add(lease)
                self.probe = lease
                return lease
            changed = self.changed
            if not self.active and self.probe is None and delay > 0:
                try:
                    await asyncio.wait_for(changed.wait(), timeout=delay)
                except TimeoutError:
                    pass
            else:
                await changed.wait()

    def finish(self, lease, *, success=False):
        """Release ownership even on cancellation; only a current probe opens the gate."""
        if lease not in self.active:
            return
        self.active.remove(lease)
        if self.probe is lease:
            self.probe = None
            if success and lease.generation == self.generation:
                self.recovering = False
        self._notify()
