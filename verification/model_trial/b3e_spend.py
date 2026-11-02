"""Finite B3e campaign ledger: USD20 across every arm, smoke and failure.

The old ABC in-memory budget is intentionally unchanged. This thin durable
adapter retains immutable reservation/settlement events, serializes callers
across processes, and stops after any unresolved attempt. Complete trusted
usage can settle known expenditure; it never refunds expenditure already made.
No credentials, model client or engine modules are imported here.
"""
from contextlib import contextmanager,closing
import hashlib,json,os,sqlite3,threading,time
from pathlib import Path
from .spend import SpendRejected,_identity

CAP_MICRO_USD=20_000_000
_THREADS={};_GUARD=threading.Lock()


def need(value,reason):
    if not value:raise SpendRejected('b3e_'+reason)


def money(value):
    need(type(value) is int and 0<=value<=CAP_MICRO_USD,'integer_micro_usd');return value


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,ensure_ascii=True).encode()
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def hex_sha(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


@contextmanager
def _file_lock(path,timeout):
    """Stable sidecar inode; only a finite campaign, no general lock service."""
    end=time.monotonic()+timeout
    with _GUARD:lock=_THREADS.setdefault(str(path),threading.Lock())
    need(lock.acquire(timeout=timeout),'busy')
    try:
        with path.open('a+b') as handle:
            handle.seek(0,2)
            if not handle.tell():handle.write(b'0');handle.flush()
            while True:
                try:
                    handle.seek(0)
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except OSError:
                    need(time.monotonic()<end,'busy');time.sleep(min(.01,max(0,end-time.monotonic())))
            try:yield
            finally:
                handle.seek(0)
                if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
    finally:lock.release()


class CampaignLedger:
    def __init__(self,path,campaign_id,authorization_sha256):
        self.path=Path(path);need(self.path.is_absolute() and self.path.resolve()==self.path and self.path.is_file(),'existing_ledger_required')
        self.campaign_id=_identity(campaign_id,'campaign_id');need(hex_sha(authorization_sha256),'authorization_digest')
        self.authorization_sha256=authorization_sha256;self.lock=self.path.with_name(self.path.name+'.call.lock')

    @classmethod
    def create(cls,path,campaign_id,authorization_sha256,*,legacy=None):
        """Trusted one-time setup; NEVER auto-create another allowance on restart.

        A handoff with previous calls must import its final record, not use
        legacy=None. A pending legacy request stops this campaign immediately.
        The trusted runner freezes this one path/campaign/authorization binding.
        """
        path=Path(path);need(path.is_absolute() and path.resolve()==path,'ledger_path')
        _identity(campaign_id,'campaign_id');need(hex_sha(authorization_sha256),'authorization_digest')
        if legacy is not None:
            need(type(legacy) is dict and set(legacy)=={'source_sha256','campaign_id','known_charge_micro_usd','pending_upper_micro_usd','unknown_requests'},'legacy_fields')
            need(hex_sha(legacy['source_sha256']) and legacy['campaign_id']==campaign_id,'legacy_binding')
            money(legacy['known_charge_micro_usd']);money(legacy['pending_upper_micro_usd'])
            need(type(legacy['unknown_requests']) is list and len(legacy['unknown_requests'])<=256,'legacy_unknowns')
            for request in legacy['unknown_requests']:_identity(request,'legacy_request')
            need(len(set(legacy['unknown_requests']))==len(legacy['unknown_requests']),'legacy_duplicate')
            need(legacy['known_charge_micro_usd']+legacy['pending_upper_micro_usd']<=CAP_MICRO_USD,'legacy_cap')
            need(bool(legacy['unknown_requests'])==(legacy['pending_upper_micro_usd']>0),'legacy_pending')
        path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        with closing(sqlite3.connect(path)) as db,db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE binding (campaign TEXT, authorization TEXT, cap INTEGER)')
            db.execute('INSERT INTO binding VALUES (?,?,?)',(campaign_id,authorization_sha256,CAP_MICRO_USD))
            db.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)')
            db.execute("CREATE TRIGGER immutable_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END")
            db.execute("CREATE TRIGGER immutable_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END")
            if legacy is not None:db.execute('INSERT INTO events(kind,payload) VALUES (?,?)',('legacy',encoded(legacy).decode()))
        return cls(path,campaign_id,authorization_sha256)

    @contextmanager
    def _transaction(self):
        need(self.path.is_file(),'missing_ledger')
        db=sqlite3.connect(self.path,timeout=2,isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            need(db.execute('SELECT campaign,authorization,cap FROM binding').fetchall()==[(self.campaign_id,self.authorization_sha256,CAP_MICRO_USD)],'binding')
            yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    @staticmethod
    def _append(db,kind,payload):
        value=encoded(payload);need(len(value)<=16384,'event_size')
        db.execute('INSERT INTO events(kind,payload) VALUES (?,?)',(kind,value.decode()))

    def _fold(self,db):
        rows=db.execute('SELECT seq,kind,payload FROM events ORDER BY seq').fetchall();need(len(rows)<=770,'event_limit')
        state=dict(cap_micro_usd=CAP_MICRO_USD,exposure_micro_usd=0,known_charge_micro_usd=0,reservations={},stopped=None,legacy=None,events=len(rows))
        for seq,kind,blob in rows:
            value=json.loads(blob)
            if kind=='legacy':
                need(seq==1 and state['legacy'] is None,'legacy_once');state['legacy']=value
                state['known_charge_micro_usd']=money(value['known_charge_micro_usd'])
                state['exposure_micro_usd']=state['known_charge_micro_usd']+money(value['pending_upper_micro_usd'])
                if value['unknown_requests']:state['stopped']='legacy_unknown_request'
            elif kind=='reserve':
                key=value['request_id'];need(key not in state['reservations'] and state['stopped'] is None,'event_reservation')
                state['exposure_micro_usd']+=money(value['upper_micro_usd']);state['reservations'][key]=dict(value,phase='reserved')
            elif kind=='settle':
                row=state['reservations'].get(value['request_id']);need(row is not None and row['phase']=='reserved','event_settlement')
                amount=money(value['charge_micro_usd']);need(amount<=row['upper_micro_usd'],'settlement_upper_bound')
                state['exposure_micro_usd']-=row['upper_micro_usd']-amount;state['known_charge_micro_usd']+=amount
                row.update(phase='settled',settlement=value)
            elif kind=='stop':state['stopped']=value['reason']
            else:need(False,'unknown_event')
            need(0<=state['known_charge_micro_usd']<=state['exposure_micro_usd']<=CAP_MICRO_USD,'corrupt_total')
        state['remaining_micro_usd']=CAP_MICRO_USD-state['exposure_micro_usd'];return state

    def snapshot(self):
        with self._transaction() as db:return self._fold(db)

    @contextmanager
    def attempt(self,episode_id,request_id,request_sha256,upper_micro_usd,*,timeout=2.):
        _identity(episode_id,'episode_id');_identity(request_id,'request_id');need(hex_sha(request_sha256),'request_digest')
        money(upper_micro_usd);need(upper_micro_usd>0 and type(timeout) in (int,float) and 0<timeout<=10,'reservation')
        with _file_lock(self.lock,timeout):
            refusal=None
            with self._transaction() as db:
                state=self._fold(db)
                if state['stopped']:refusal='stopped_'+state['stopped']
                elif any(row['phase']=='reserved' for row in state['reservations'].values()):
                    self._append(db,'stop',dict(reason='prior_request_unreconciled'));refusal='prior_request_unreconciled'
                elif request_id in state['reservations']:refusal='request_id_reused'
                elif len(state['reservations'])>=256:refusal='request_limit'
                elif upper_micro_usd>state['remaining_micro_usd']:refusal='campaign_cap'
                else:self._append(db,'reserve',dict(episode_id=episode_id,request_id=request_id,request_sha256=request_sha256,upper_micro_usd=upper_micro_usd))
            need(refusal is None,refusal or 'reservation_refused')
            permit=_Attempt(self,request_id)
            try:yield permit
            finally:
                with self._transaction() as db:
                    state=self._fold(db)
                    if state['reservations'][request_id]['phase']=='reserved' and not state['stopped']:
                        self._append(db,'stop',dict(reason='request_outcome_unknown',request_id=request_id))


class _Attempt:
    def __init__(self,ledger,request_id):self.ledger=ledger;self.request_id=request_id
    def settle(self,charge_micro_usd,receipt):
        money(charge_micro_usd)
        need(type(receipt) is dict and hex_sha(receipt.get('response_sha256')) and hex_sha(receipt.get('price_sha256'))
             and type(receipt.get('model_version')) is str and receipt['model_version'] and type(receipt.get('usage')) is dict,'trusted_complete_receipt')
        with self.ledger._transaction() as db:
            state=self.ledger._fold(db);row=state['reservations'][self.request_id]
            need(state['stopped'] is None and row['phase']=='reserved' and charge_micro_usd<=row['upper_micro_usd'],'settlement')
            self.ledger._append(db,'settle',dict(request_id=self.request_id,charge_micro_usd=charge_micro_usd,receipt=receipt))
