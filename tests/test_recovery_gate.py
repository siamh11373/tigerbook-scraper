import asyncio

from tigerbook_scraper.recovery_gate import RecoveryGate


def test_drain_then_exactly_one_probe_and_ignore_old_success():
    async def run():
        gate = RecoveryGate()
        first, second = await gate.enter(), await gate.enter()
        gate.block(0)
        pending = [asyncio.create_task(gate.enter()) for _ in range(3)]
        await asyncio.sleep(0)
        assert not any(task.done() for task in pending)
        gate.finish(first, success=True)
        await asyncio.sleep(0)
        assert not any(task.done() for task in pending)
        gate.finish(second, success=True)
        await asyncio.sleep(0)
        done = [task for task in pending if task.done()]
        assert len(done) == 1
        probe = done[0].result()
        assert probe.probe and gate.recovering
        gate.finish(probe, success=True)
        leases = await asyncio.wait_for(asyncio.gather(*pending), 1)
        for lease in leases:
            gate.finish(lease)
        assert not gate.active and not gate.recovering

    asyncio.run(run())


def test_failed_probe_and_new_block_do_not_reopen():
    async def run():
        gate = RecoveryGate()
        gate.block(0)
        probe = await gate.enter()
        gate.block(0)
        gate.finish(probe, success=True)
        assert gate.recovering
        probe = await gate.enter()
        gate.finish(probe)
        assert gate.recovering
        next_probe = await asyncio.wait_for(gate.enter(), 1)
        assert next_probe.probe
        gate.finish(next_probe, success=True)
        assert not gate.recovering

    asyncio.run(run())


def test_cancelled_waiter_and_probe_release_without_deadlock():
    async def run():
        gate = RecoveryGate()
        gate.block(0)
        probe = await gate.enter()
        waiter = asyncio.create_task(gate.enter())
        await asyncio.sleep(0)
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        gate.finish(probe)
        replacement = await asyncio.wait_for(gate.enter(), 1)
        gate.finish(replacement, success=True)
        assert not gate.active

    asyncio.run(run())


def test_cooldown_extension_is_honored():
    async def run():
        now = [0.0]
        gate = RecoveryGate(clock=lambda: now[0])
        gate.block(10)
        waiter = asyncio.create_task(gate.enter())
        await asyncio.sleep(0)
        now[0] = 5
        gate.block(10)
        assert gate.blocked_until == 15
        await asyncio.sleep(0)
        assert not waiter.done()
        now[0] = 15
        gate.block(0)
        probe = await asyncio.wait_for(waiter, 1)
        assert probe.probe
        gate.finish(probe, success=True)

    asyncio.run(run())


class ImmediateThrottle:
    async def wait(self):
        return None

    def success(self):
        pass

    def failure(self):
        pass

    def cooldown(self, _seconds):
        pass


class ImmediateRecovery(RecoveryGate):
    def block(self, _seconds):
        super().block(0)


class JsonResponse:
    url = "https://tigernet.princeton.edu/example"
    headers = {"content-type": "application/json"}

    def __init__(self, status=200):
        self.status = status

    async def text(self):
        return "{}"

    async def dispose(self):
        pass


def test_client_shared_admission_drains_wave_then_one_probe():
    from tigerbook_scraper.errors import AccessBlocked
    from tigerbook_scraper.fast import Client

    async def run():
        gate, admission = ImmediateRecovery(), asyncio.Lock()
        slots, throttle = asyncio.Semaphore(8), ImmediateThrottle()
        started = []
        release = {name: asyncio.Event() for name in ("first", "second", "probe", "last")}

        class Request:
            async def get(self, url, **_kwargs):
                name = url.rsplit("/", 1)[-1]
                started.append(name)
                await release[name].wait()
                return JsonResponse(429 if name == "first" else 200)

        clients = [
            Client(Request(), throttle, slots=slots, recovery=gate, admission=admission, attempts=1)
            for _ in range(2)
        ]
        first = asyncio.create_task(clients[0].get(JsonResponse.url + "/first"))
        second = asyncio.create_task(clients[1].get(JsonResponse.url + "/second"))
        await asyncio.sleep(0)
        release["first"].set()
        result = await asyncio.gather(first, return_exceptions=True)
        assert isinstance(result[0], AccessBlocked)
        probe = asyncio.create_task(clients[0].get(JsonResponse.url + "/probe"))
        last = asyncio.create_task(clients[1].get(JsonResponse.url + "/last"))
        await asyncio.sleep(0)
        assert started == ["first", "second"]
        release["second"].set()
        await second
        await asyncio.sleep(0)
        assert started == ["first", "second", "probe"]
        assert gate.recovering
        release["probe"].set()
        await probe
        await asyncio.sleep(0)
        assert started == ["first", "second", "probe", "last"]
        release["last"].set()
        await last
        assert not gate.active and not admission.locked()

    asyncio.run(asyncio.wait_for(run(), 2))


def test_client_cancelled_probe_releases_lease_and_admission():
    from tigerbook_scraper.fast import Client

    async def run():
        gate = ImmediateRecovery()
        gate.block(0)
        started = asyncio.Event()

        class Request:
            async def get(self, _url, **_kwargs):
                started.set()
                await asyncio.Event().wait()

        client = Client(Request(), ImmediateThrottle(), recovery=gate)
        task = asyncio.create_task(client.get(JsonResponse.url))
        await started.wait()
        task.cancel()
        result = await asyncio.gather(task, return_exceptions=True)
        assert isinstance(result[0], asyncio.CancelledError)
        assert not gate.active and gate.probe is None and gate.recovering
        assert not client.admission.locked()
        lease = await gate.enter()
        gate.finish(lease, success=True)

    asyncio.run(asyncio.wait_for(run(), 2))
