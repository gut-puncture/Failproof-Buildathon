#!/usr/bin/env python3
"""Portable Failproof Cloud identity and explicit saved-evidence export.

Default export is local only. --upload sends the reviewed summary to Cloud.
This imports a saved record; it does not claim a fresh run or a deployed policy.
Sources:
https://docs.befailproof.ai/start/integrations/custom-agents
https://docs.befailproof.ai/reference/openapi.json
https://github.com/FailproofAI/failproofai/blob/main/sdk/python/failproofai_sdk/_schema.py
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid

BASE = 'https://app.befailproof.ai'
FIELDS = {'checkId', 'version', 'checkHash', 'requestHash', 'timestamp', 'mode',
          'thresholds', 'scores', 'decision', 'reason', 'elapsedMs', 'httpStatus',
          'fixtureId', 'expectedViolation', 'expectedApplicable', 'nativePolicy'}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def credential():
    value = os.environ.get('FAILPROOF_API_KEY', '').strip()
    if not value:
        name = os.environ.get('FAILPROOF_KEY_FILE')
        if name:
            value = Path(name).read_text(encoding='utf-8').strip()
    if not value:
        raise ValueError('Set FAILPROOF_API_KEY or FAILPROOF_KEY_FILE')
    return value


def request(path, data=None):
    req = Request(BASE + path, data=data, headers={
        'Authorization': 'Bearer ' + credential(),
        'Content-Type': 'application/x-ndjson' if data is not None else 'application/json',
    }, method='POST' if data is not None else 'GET')
    try:
        with build_opener(NoRedirect()).open(req, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError('Failproof request rejected (HTTP %d)' % exc.code) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise RuntimeError('Failproof request or response unavailable') from None


def identity():
    raw = request('/v1/auth/introspect')
    if raw.get('valid') is False or not isinstance(raw.get('permissions'), list):
        raise RuntimeError('Identity response was not valid')
    return {'verified_at': datetime.now(timezone.utc).isoformat(),
            'source': BASE + '/v1/auth/introspect',
            **{k: raw[k] for k in ('org_id', 'org_slug', 'org_name', 'permissions') if k in raw}}


def result_summary(row):
    return {k: v for k, v in row.items() if k in FIELDS}


def build_events(record):
    if not isinstance(record, dict):
        raise ValueError('RUN.json must contain an object')
    # Read only the explicit JSON file; never traverse paths inside a record.
    encoded = json.dumps(record, sort_keys=True, separators=(',', ':')).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    session = 'semantic-loop-import-' + uuid.uuid5(uuid.NAMESPACE_URL, digest).hex
    stamp = datetime.now(timezone.utc)
    summary = {k: record[k] for k in ('kind', 'decision', 'reason', 'summary') if k in record}
    rows = record.get('results', [record] if 'scores' in record else [])
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('results must be an array of result objects')
    summary['results'] = [result_summary(row) for row in rows]
    correction = record.get('correction')
    if isinstance(correction, dict):
        summary['correction'] = {k: correction[k] for k in ('outcome', 'decision', 'reason', 'independentTests') if k in correction}
        after = correction.get('after', [])
        summary['correction']['after'] = [result_summary(r) for r in after if isinstance(r, dict)]
    if not summary['results'] and not summary.get('decision'):
        raise ValueError('No guard results or decision in RUN.json')
    shared = {'session_id': session, 'agent_id': 'semantic-check-loop',
              'environment': 'hackathon-evidence-import',
              'evidence_provenance': 'Explicit import of a saved local record; not a new execution.',
              'artifact_sha256': digest}
    def event(index, kind, **fields):
        return {'timestamp': (stamp + timedelta(milliseconds=index)).isoformat(),
                **shared, 'type': kind, **fields}
    events = [
        event(0, 'agent_start', goal='Import saved semantic-check loop evidence'),
        event(1, 'tool_use', tool_name='import_saved_semantic_check', tool_call_id=session + '-import',
              input={'artifact_sha256': digest, 'content': 'Selected verdict metadata only; no task or source text.'}),
        event(2, 'tool_result', tool_name='import_saved_semantic_check', tool_call_id=session + '-import', output=summary),
        event(3, 'agent_end', outcome='success', summary='Saved evidence imported; original semantic decision is in tool_result.'),
    ]
    return events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--identity', action='store_true', help='Read organization metadata only')
    mode.add_argument('--export', metavar='RUN.json', help='Write native events locally; no network')
    mode.add_argument('--upload', metavar='RUN.json', help='Explicitly send selected saved verdict metadata to Failproof Cloud')
    parser.add_argument('--out', help='Write identity JSON or events NDJSON to this new file')
    args = parser.parse_args()
    if args.identity:
        result = identity()
        content = json.dumps(result, indent=2) + '\n'
    else:
        filename = args.export or args.upload
        path = Path(filename)
        if path.stat().st_size > 5_000_000:
            raise ValueError('RUN.json exceeds the 5 MB import limit')
        events = build_events(json.loads(path.read_text(encoding='utf-8')))
        content = ''.join(json.dumps(e, separators=(',', ':')) + '\n' for e in events)
        result = {'session_id': events[0]['session_id'], 'event_count': len(events),
                  'uploaded': False, 'source': str(path),
                  'scope': 'Saved verdict metadata import; not a live policy deployment or native evaluation.'}
        if args.upload:
            org = identity()
            if 'events:add' not in org['permissions']:
                raise RuntimeError('The key does not have events:add permission')
            response = request('/v1/events', content.encode())
            accepted, skipped = response.get('accepted'), response.get('skipped')
            if accepted != len(events) or skipped != 0:
                raise RuntimeError('Upload not verified: accepted=%r skipped=%r' % (accepted, skipped))
            result.update(uploaded=True, accepted=accepted, skipped=skipped,
                          org_id=org.get('org_id'), org_slug=org.get('org_slug'))
    if args.out:
        with Path(args.out).open('x', encoding='utf-8') as out:
            out.write(content)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        # Do not echo HTTP response bodies or credentials.
        print('Failproof adapter: ' + str(error), file=sys.stderr)
        sys.exit(1)
