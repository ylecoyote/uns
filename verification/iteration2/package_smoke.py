"""Run against the installed full wheel, from outside the source checkout."""
import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from agsignal.responses import SendNotificationRequest
from notification.adapters.base import AdapterStatus, BaseAdapter, DeliveryResult, HealthCheckResult
from notification.models import Channel
from notification.policies import PolicyRegistry, configure_policy_registry
from notification.service import SimpleAdapterRegistry
from uns.maintenance import maintain
from uns.runtime import Runtime
from uns.schema import migrate_runtime_schema


class Recorder(BaseAdapter):
    channel = Channel.SLACK
    async def deliver(self, notification):
        return DeliveryResult(success=True, channel=self.channel)
    async def health_check(self):
        return HealthCheckResult(AdapterStatus.HEALTHY, 'local recorder')


async def main():
    repository = Path(sys.argv[1])
    if str(repository / 'src') in str(__import__('uns.runtime', fromlist=['__file__']).__file__):
        raise RuntimeError('Smoke must use installed wheel')
    configure_policy_registry(registry=PolicyRegistry())
    registry = SimpleAdapterRegistry()
    registry.register(Recorder())
    with tempfile.TemporaryDirectory(prefix='uns-iteration2-wheel-') as folder:
        path = Path(folder) / 'store.db'
        runtime = Runtime(f'sqlite:///{path}', create_tables=True, adapters=registry, clock=lambda: 1000.0)
        request = SendNotificationRequest(notification_type='smoke', intent='SAFETY', title='local smoke',
            message='No external provider', source='installed-smoke', idempotency_key='one',
            autonomy_context={'agent_id':'00000000-0000-0000-0000-000000000001','autonomy_mode':'LIVE'})
        accepted = await runtime.send(request, principal='operator')
        assert accepted.status.value == 'DELIVERED'
        runtime.acknowledge(accepted.notification_id, actor='operator')
        before = runtime.get(accepted.notification_id)
        for _ in range(2):
            migrated = subprocess.run([str(Path(sys.executable).parent/'uns-migrate')], env={**os.environ, 'UNS_DATABASE_URL':f'sqlite:///{path}'}, capture_output=True, text=True, timeout=20)
            assert migrated.returncode == 0, migrated.stderr
        migrate_runtime_schema(runtime.engine)
        migrate_runtime_schema(runtime.engine)
        assert runtime.get(accepted.notification_id) == before
        assert 'dedup_successor_id' in before
        snapshot = path.read_bytes()
        report = maintain(runtime.engine, cutoff=5000, idempotency_seconds=60, now=10000)
        assert report['deleted_rows'] == 2
        assert path.read_bytes() == snapshot
        assert runtime.get(accepted.notification_id)['ack_status'] == 'ACKED'
        runtime.engine.dispose()
    wheel = next((repository / 'dist').glob('*.whl'))
    with ZipFile(wheel) as archive:
        shipped = [name for name in archive.namelist() if name.endswith('.py') and '.dist-info/' not in name]
        for name in shipped:
            assert archive.read(name) == (repository/'src'/name).read_bytes(), name
        print(f'Wheel/source identity: {len(shipped)} modules')
    for command in ('uns-maintain', 'uns-mcp'):
        output = subprocess.run([str(Path(sys.executable).parent / command), '--help'], capture_output=True, text=True, timeout=20)
        assert output.returncode == 0, (command, output.stderr)
    print('Installed full wheel delivery/ACK, repeated migration, no-write retention preview and CLI smoke passed')
    print('Wheel sha256:', hashlib.sha256(wheel.read_bytes()).hexdigest())


asyncio.run(main())
