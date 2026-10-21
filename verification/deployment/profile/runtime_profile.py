"""Isolated recording-only smoke composition. Never use as a live provider profile."""
import json
import os
from pathlib import Path
from notification.adapters.base import BaseAdapter,DeliveryResult,AdapterStatus,HealthCheckResult
from notification.models import Channel,DeliveryMode,NotificationIntent
from notification.policies import NotificationPolicy
from db.policy_store import SQLAlchemyPolicyStore
from uns.config import build_runtime

class Recorder(BaseAdapter):
    channel=Channel.SLACK
    async def deliver(self,n):
        success=not(n.metadata.get('smoke_fail') and not Path('/data/allow-recovery').exists())
        with Path('/data/recordings.jsonl').open('a') as f:
            f.write(json.dumps({'id':str(n.notification_id),'success':success,'channel':'SLACK','source':n.source})+'\n')
        return DeliveryResult(success=success,channel=self.channel,message_id='recording:'+str(n.notification_id),error=None if success else 'injected local recorder failure')
    async def health_check(self):
        return HealthCheckResult(AdapterStatus.HEALTHY,'Isolated recording adapter; no external delivery')

async def callback(event):
    with Path('/data/callbacks.jsonl').open('a') as f:
        f.write(json.dumps({'id':event['id'],'notification_id':event['notification_id'],'kind':event['kind'],'attempt':event['callback_attempts']})+'\n')
    if event['callback_attempts']==1:
        raise RuntimeError('injected first callback failure')

def make_runtime():
    runtime=build_runtime()
    runtime.adapters.register(Recorder())
    runtime.callback=callback
    if not runtime.policy_runtime.registry().get('smoke.safety'):
        policy=NotificationPolicy(notification_type='smoke.safety',version='1',intent=NotificationIntent.SAFETY,
            channels=[Channel.SLACK],delivery_mode=DeliveryMode.GUARANTEED,require_ack=True,ack_timeout_minutes=1)
        SQLAlchemyPolicyStore(runtime.sessions).save_snapshot([policy])
    return runtime
