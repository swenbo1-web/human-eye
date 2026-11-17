"""Opt-in bounded episode/source archive and read-only restart inspection.

No archive JSON reconstructs a live task or a writable archive slot. Missing
terminal evidence is unknown, including a crash before the first action. Hashes
check consistency, not authenticity. Directory power-loss durability is unproven.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import tempfile

from .task_authority import _spec_from_dict, _scope
from .task_episode import validate_episode, task_event_id, MAX_DOCUMENT_BYTES, _number

MAX_SLOTS = 16
MAX_SOURCE_BYTES = 4*1024*1024
HEX = re.compile(r'[0-9a-f]{64}\Z')
NAMES = ('intake.json', 'source.json', 'final.json')


def _need(value, reason):
    if not value:raise ValueError(reason)


def _bytes(value, limit=MAX_SOURCE_BYTES):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,ensure_ascii=True).encode('utf8')
    _need(len(raw)<=limit,'archive_document_budget')
    return raw


def _digest(value):return hashlib.sha256(_bytes(value)).hexdigest()


def _sealed(schema, **fields):
    doc=json.loads(_bytes(dict(schema=schema,**fields)));doc['sha256']=_digest(doc);return doc


def _validate(doc, schema):
    _need(type(doc) is dict and doc.get('schema')==schema,'archive_schema_mismatch')
    copy=dict(doc);claimed=copy.pop('sha256',None)
    _need(type(claimed) is str and HEX.fullmatch(claimed) and claimed==_digest(copy),'archive_digest_mismatch')
    return doc


def _read(folder,name,limit):
    _need(name in NAMES,'archive_fixed_name_required')
    path=folder/name
    _need(not path.is_symlink() and path.resolve().parent==folder,'archive_path_changed')
    with path.open('rb') as f:raw=f.read(limit+1)
    _need(len(raw)<=limit,'archive_document_budget')
    return json.loads(raw,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('archive_nonfinite')))


def _publish(folder,name,doc,limit):
    _need(name in NAMES,'archive_fixed_name_required');raw=_bytes(doc,limit)
    pending=None
    try:
        with tempfile.NamedTemporaryFile(mode='wb',dir=folder,prefix='.pending-',delete=False) as f:
            pending=Path(f.name);f.write(raw);f.flush();os.fsync(f.fileno())
        try:os.link(pending,folder/name)
        except FileExistsError:
            _need(_read(folder,name,limit)==doc,'archive_existing_conflict')
    finally:
        if pending is not None:pending.unlink()
    return dict(sha256=doc['sha256'],file_flushed=True,directory_metadata_flushed=False)


def _intake(value):
    required={'event_id','connection_id','request_id','request_sha256','received_monotonic','origin'}
    _need(type(value) is dict and set(value)==required,'archive_intake_fields')
    _need(value['event_id']==task_event_id(value['connection_id'],value['request_id']),'archive_event_mismatch')
    _need(type(value['request_sha256']) is str and HEX.fullmatch(value['request_sha256']),'archive_request_digest')
    _need(value['origin']=='stdio_client_response_human_unverified','archive_origin_invalid')
    _need(value['received_monotonic'] is None or _number(value['received_monotonic']),'archive_receive_time_invalid')
    return json.loads(_bytes(value,4096))


def _source(doc,intake):
    _validate(doc,'owned-episode-source-v1')
    _need(set(doc)=={'schema','sha256','intake_sha256','task','scope','packet'},'archive_source_fields')
    _need(doc['intake_sha256']==intake['sha256'],'archive_source_intake_mismatch')
    spec=_spec_from_dict(doc['task']);scope=_scope(doc['scope'],spec)
    packet=doc['packet']
    _need(type(packet) is dict and set(packet)=={'capture','native_scene','capture_confirmation_sha256'},'archive_source_packet_fields')
    _need(_digest(packet['capture'])==scope['initial_capture_sha256'] and
          _digest(packet['native_scene'])==scope['initial_native_sha256'] and
          packet['capture_confirmation_sha256']==scope['initial_capture_sha256'] and
          packet['capture'].get('host_identity')==scope['host_identity'], 'archive_source_snapshot_mismatch')
    return doc


@dataclass(frozen=True)
class _Slot:
    index:int
    event_id:str
    intake_sha256:str


class EpisodeArchive:
    """One operator-selected existing directory; no eviction or writable resume.

    Exactly 16 lifetime slots, each with at most intake/source/final. Restart
    reads old slots but never recreates their writer objects. Fixed filenames
    and bounded scans avoid unbounded manifests and per-event directory walks.
    """
    def __init__(self,directory,*,max_slots=MAX_SLOTS):
        _need(type(max_slots) is int and 1<=max_slots<=MAX_SLOTS,'archive_slot_limit')
        self.root=Path(directory).resolve(strict=True);self.max_slots=max_slots;self._active={}
        self._folders()

    def _folders(self):
        _need(self.root.is_dir() and not self.root.is_symlink() and self.root.resolve()==self.root,'archive_root_changed')
        entries=list(islice(self.root.iterdir(),self.max_slots+1))
        _need(len(entries)<=self.max_slots,'archive_capacity_or_foreign_entries')
        result={}
        for p in entries:
            match=re.fullmatch(r'slot-([0-9]{2})',p.name)
            _need(match is not None and p.is_dir() and not p.is_symlink() and p.resolve()==p,'archive_foreign_or_linked_slot')
            index=int(match[1]);_need(index<self.max_slots,'archive_slot_out_of_range');result[index]=p
        return result

    def _writer(self,slot):
        _need(type(slot) is _Slot and self._active.get(slot.index) is slot,'archive_original_live_writer_required')
        return self._folders()[slot.index]

    def begin(self,intake):
        value=_intake(intake);folders=self._folders()
        # Lifetime slots are never recycled, including empty/crashed slots.
        for folder in folders.values():
            try:prior=_read(folder,'intake.json',8192)
            except (OSError,ValueError):continue
            _need(prior.get('intake',{}).get('event_id')!=value['event_id'],'archive_event_already_present')
        for index in range(self.max_slots):
            if index in folders:continue
            folder=self.root/('slot-%02d'%index)
            try:folder.mkdir()
            except FileExistsError:continue
            doc=_sealed('owned-episode-intake-v1',intake=value)
            _publish(folder,'intake.json',doc,8192)
            slot=_Slot(index,value['event_id'],doc['sha256']);self._active[index]=slot
            return slot
        raise ValueError('archive_lifetime_capacity_reached')

    def bind_source(self,slot,task,scope,packet):
        folder=self._writer(slot);intake=_validate(_read(folder,'intake.json',8192),'owned-episode-intake-v1')
        _need(type(packet) is dict and set(packet)=={'capture','native_scene','capture_confirmation'},'archive_original_capture_packet_required')
        confirmation=_digest(packet['capture_confirmation'])
        _need(confirmation==_digest(packet['capture']),'archive_confirmation_changed')
        # The producer's confirmed capture is canonically identical. Retain
        # its digest and original relation without duplicating its geometry.
        retained=dict(capture=packet['capture'],native_scene=packet['native_scene'],
                      capture_confirmation_sha256=confirmation)
        doc=_sealed('owned-episode-source-v1',intake_sha256=slot.intake_sha256,task=task,scope=scope,packet=retained)
        _source(doc,intake)
        return _publish(folder,'source.json',doc,MAX_SOURCE_BYTES)

    def finish(self,slot,episode):
        folder=self._writer(slot);episode=validate_episode(episode)
        intake=_validate(_read(folder,'intake.json',8192),'owned-episode-intake-v1')
        original=intake['intake'];raw=episode['raw_evidence']
        _need(all(raw.get(k)==v for k,v in original.items()),'archive_episode_intake_mismatch')
        source=None
        if (folder/'source.json').exists():source=_source(_read(folder,'source.json',MAX_SOURCE_BYTES),intake)
        if raw['binding'] is not None:
            _need(source is not None and raw['binding']=={'task':source['task'],'scope':source['scope']},'archive_episode_source_missing_or_changed')
        doc=_sealed('owned-episode-final-v1',intake_sha256=intake['sha256'],
                    source_sha256=source['sha256'] if source else None,episode=episode)
        return _publish(folder,'final.json',doc,MAX_DOCUMENT_BYTES+16384)

    def recover(self):
        rows=[]
        for index,folder in sorted(self._folders().items()):
            row=dict(slot=index,event_id=None,status='unknown',reason='terminal_evidence_missing',
                     recorded_outcome=None,recorded_new_setter_count=None,source_verified=False,
                     execution_authority=False,retry_authorized=False,training_positive=False,human_UI_verified=False)
            try:
                entries=list(islice(folder.iterdir(),9));_need(len(entries)<=8,'archive_slot_entry_budget')
                _need(all(p.name in NAMES or p.name.startswith('.pending-') for p in entries),'archive_foreign_slot_file')
                row['orphaned_temporary_files_seen']=sum(p.name.startswith('.pending-') for p in entries)
                intake=_validate(_read(folder,'intake.json',8192),'owned-episode-intake-v1')
                _need(set(intake)=={'schema','sha256','intake'},'archive_intake_envelope_fields');_intake(intake['intake'])
                row.update(event_id=intake['intake']['event_id'],intake_sha256=intake['sha256'])
                source=None
                if (folder/'source.json').exists():
                    source=_source(_read(folder,'source.json',MAX_SOURCE_BYTES),intake)
                    row.update(source_sha256=source['sha256'],source_verified=True)
                final=_validate(_read(folder,'final.json',MAX_DOCUMENT_BYTES+16384),'owned-episode-final-v1')
                _need(set(final)=={'schema','sha256','intake_sha256','source_sha256','episode'},'archive_final_fields')
                _need(final['intake_sha256']==intake['sha256'] and
                      final['source_sha256']==(source['sha256'] if source else None),'archive_final_binding_mismatch')
                episode=validate_episode(final['episode']);raw=episode['raw_evidence']
                _need(all(raw.get(k)==v for k,v in intake['intake'].items()),'archive_episode_intake_mismatch')
                if raw['binding'] is not None:
                    _need(source is not None and raw['binding']=={'task':source['task'],'scope':source['scope']},'archive_episode_source_missing_or_changed')
                row.update(status='recorded_terminal',reason=None,episode_sha256=episode['sha256'],
                           recorded_outcome=episode['derived']['outcome'],
                           recorded_new_setter_count=episode['derived']['new_setter_count'])
            except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
                row['reason']=str(exc)[:160] if isinstance(exc,ValueError) else type(exc).__name__
            rows.append(row)
        counts=Counter(row['event_id'] for row in rows if row['event_id'] is not None)
        for row in rows:
            if row['event_id'] is not None and counts[row['event_id']]>1:
                row.update(status='unknown',reason='archive_duplicate_event_conflict',
                           recorded_outcome=None,recorded_new_setter_count=None)
        return dict(schema='owned-episode-recovery-v1',slots_observed=len(rows),max_slots=self.max_slots,
                    rows=rows,terminal_records=sum(r['status']=='recorded_terminal' for r in rows),
                    unknown_records=sum(r['status']=='unknown' for r in rows),distinct_recorded_events=len(counts),
                    recorded_outcomes=dict(Counter(r['recorded_outcome'] for r in rows if r['recorded_outcome'] is not None)),
                    uncertain_task_records=sum(r['status']=='unknown' or r['recorded_outcome']=='unknown' for r in rows),
                    independent_support_count=None,execution_authority=False,retry_authorized=False,
                    training_positives=0,presentation_scope='historical_files_not_current_scene',
                    human_UI_verified=0,directory_power_loss_durability_certified=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Read-only bounded Human Eye archive recovery; never dispatch')
    parser.add_argument('--root',type=Path,required=True);args=parser.parse_args(argv)
    print(json.dumps(EpisodeArchive(args.root).recover(),ensure_ascii=True,allow_nan=False))


if __name__=='__main__':main()
