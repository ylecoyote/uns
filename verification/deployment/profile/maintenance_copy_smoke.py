"""Destructive retention checks run only against a fresh backup of synthetic smoke data."""
import hashlib,json,sqlite3,time
from pathlib import Path
from sqlalchemy import create_engine
from uns.maintenance import maintain
original=sqlite3.connect('/data/uns.db')
before=original.execute('select count(*) from uns_notifications').fetchone()[0]
copy_path=Path('/data/retention-copy.db')
if copy_path.exists():raise RuntimeError('Refuse to overwrite prior retention evidence')
with sqlite3.connect(copy_path) as backup:
    original.backup(backup)
engine=create_engine('sqlite:////data/retention-copy.db')
now=time.time()
checksum=hashlib.sha256(copy_path.read_bytes()).hexdigest()
preview=maintain(engine,cutoff=now+3600,idempotency_seconds=60,now=now+7200)
assert hashlib.sha256(copy_path.read_bytes()).hexdigest()==checksum
archive=Path('/data/retention-copy-archive.json')
result=maintain(engine,cutoff=now+3600,idempotency_seconds=60,now=now+7200,apply=True,operator='smoke-copy-only',archive=archive)
assert result['deleted_rows']>0
assert result['archive']['sha256']==hashlib.sha256(archive.read_bytes()).hexdigest()
assert original.execute('select count(*) from uns_notifications').fetchone()[0]==before
print(json.dumps({'dry_run_unchanged':True,'archive_hash_verified':True,'deleted_rows_on_copy':result['deleted_rows'],'live_notification_count_unchanged':before,'synthetic_future_cutoff_on_copy_only':True}))
