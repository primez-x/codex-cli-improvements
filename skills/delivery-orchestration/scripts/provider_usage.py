"""Read included-quota observations. Emit only normalized, sanitized JSON."""
import argparse
from contextlib import suppress
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import http.client
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

MAX_BYTES = 1024 * 1024
RPC_TIMEOUT = 15
SOURCES = {'codex': 'codex/account/rateLimits/read',
           'claude': 'anthropic/oauth/usage', 'muse': 'muse/usage/read'}


class ProbeError(Exception):
    """A read failed without a safe quota observation."""


def number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def utc(value):
    if not number(value):
        raise ValueError
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def timestamp(value):
    if number(value):
        return value
    if not isinstance(value, str):
        raise ValueError
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError
    return parsed.timestamp()


def model_family(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'(?:claude[ -])?(opus|sonnet|haiku|fable)(?:[ -][0-9.]+)?', value.lower())
    if match:
        return 'claude-' + match.group(1)
    if re.fullmatch(r'gpt-[0-9]+(?:\.[0-9]+)?(?:-(?:codex|sol|luna|astra))?', value.lower()):
        return value.lower()
    return None


def unknown(provider, reason='invalid_observation'):
    return {'status': 'unknown', 'source': SOURCES[provider], 'windows': [], 'reason': reason}


def normalized_window(identifier, scope, used, duration, reset, now, model=None):
    if not number(used) or used < 0 or not number(duration) or duration <= 0:
        raise ValueError
    reset = timestamp(reset)
    if reset <= now:
        raise ValueError
    result = {'id': identifier, 'scope': scope, 'used_percent': used,
              'remaining_percent': max(0, 100 - used), 'duration_minutes': duration,
              'resets_at': utc(reset)}
    family = model_family(model)
    if scope == 'model':
        result['model_family'] = family or 'unrecognized'
    return result


def finish(provider, windows, complete, blocked=False):
    result = {'status': 'unknown', 'source': SOURCES[provider], 'windows': windows}
    shared = [w['remaining_percent'] for w in windows if w['scope'] == 'shared']
    if blocked or (shared and min(shared) == 0):
        result['status'] = 'blocked'
    elif complete and shared:
        result['status'] = 'available'
    if result['status'] == 'blocked':
        result['headroom_percent'] = 0
    elif complete and shared:
        result['headroom_percent'] = min(shared)
    if result['status'] == 'unknown':
        result['reason'] = 'incomplete_observation'
    return result


def normalize_codex(data, now):
    if not isinstance(data, dict):
        return unknown('codex')
    main = data.get('rateLimits')
    main = main if isinstance(main, dict) else {}
    blocked = data.get('ordinaryUsageAllowed') is False or main.get('spendControlReached') is True
    windows = []
    complete = False
    groups = data.get('rateLimitsByLimitId')
    groups = list(groups.values()) if isinstance(groups, dict) else []
    for index, group in enumerate([main] + groups):
        if not isinstance(group, dict):
            continue
        model = group.get('normalModelSlug')
        scope = 'model' if model else 'shared'
        # The main group defines provider capacity. Other groups retain explicit model scope.
        if index and not model:
            continue
        valid = True
        count = 0
        for name in ('primary', 'secondary'):
            raw = group.get(name)
            if raw is None:
                continue
            try:
                entry = normalized_window(name if not index else f'model_{index}_{name}', scope,
                                          raw['usedPercent'], raw['windowDurationMins'],
                                          raw['resetsAt'], now, model)
                windows.append(entry)
                count += 1
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                valid = False
        if not index:
            complete = valid and count > 0 and scope == 'shared'
    return finish('codex', windows, complete, blocked)


def normalize_muse(data, now):
    usage = data.get('usage') if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return unknown('muse', 'no_observation')
    observed = usage.get('observedAtMs')
    if not number(observed) or not 0 <= now - observed / 1000 <= 300:
        return unknown('muse', 'stale_observation')
    windows = []
    valid = True
    for name, duration in [('window', None), ('weekly', 10080)]:
        try:
            raw = usage[name]
            windows.append(normalized_window(name, 'shared', raw['usedPercent'],
                                              raw.get('windowDurationMins', duration),
                                              raw['resetsAtMs'] / 1000
                                              if number(raw['resetsAtMs']) else None, now))
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            valid = False
    result = finish('muse', windows, valid and len(windows) == 2)
    result['observed_at'] = utc(observed / 1000)
    return result


def normalize_claude(data, now):
    if not isinstance(data, dict):
        return unknown('claude')
    windows = []
    complete = True
    limits = data.get('limits', [])
    limits = limits if isinstance(limits, list) else []
    for name, kind, duration in [('five_hour', 'session', 300), ('seven_day', 'weekly_all', 10080)]:
        raw = data.get(name)
        percent_key = 'utilization'
        if raw is None:
            raw = next((row for row in limits if isinstance(row, dict) and row.get('kind') == kind), None)
            percent_key = 'percent'
        try:
            windows.append(normalized_window(name, 'shared', raw[percent_key], duration,
                                              raw['resets_at'], now))
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            complete = False
    scoped = [(name, data.get(name), family) for name, family in
              [('seven_day_opus', 'opus'), ('seven_day_sonnet', 'sonnet')]]
    for row in limits:
        if not isinstance(row, dict) or row.get('kind') != 'weekly_scoped':
            continue
        scope = row.get('scope')
        model = scope.get('model') if isinstance(scope, dict) else None
        family = model_family(model.get('display_name')) if isinstance(model, dict) else None
        scoped.append(('weekly_scoped', row, family))
    for name, raw, model in scoped:
        try:
            entry = normalized_window(name, 'model', raw['percent' if name == 'weekly_scoped' else 'utilization'], 10080,
                                      raw['resets_at'], now, model)
            windows.append(entry)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
    return finish('claude', windows, complete)


def close_process(process, reader=None):
    """Close owned input, then stop and reap only the owned launcher."""
    if process.stdin is not None:
        with suppress(OSError):
            process.stdin.close()
    for action in (None, process.terminate, process.kill):
        if process.poll() is not None:
            break
        if action:
            with suppress(OSError):
                action()
        try:
            process.wait(timeout=1)
            break
        except subprocess.TimeoutExpired:
            continue
    if reader:
        reader.join(timeout=1)
    if reader is None or not reader.is_alive():
        with suppress(OSError):
            process.stdout.close()


def command_path(name):
    path = shutil.which(name)
    if path is None:
        raise ProbeError
    return path


def rpc_read(command, method, jsonrpc=False, timeout=RPC_TIMEOUT, env=None):
    """Read two responses from an owned process with bounded portable pipes."""
    frames = queue.Queue(maxsize=32)
    stop = threading.Event()
    process = None
    reader = None
    deadline = time.monotonic() + timeout

    def read_frames():
        total = 0
        try:
            while not stop.is_set():
                line = process.stdout.readline(MAX_BYTES + 1)
                total += len(line)
                if not line or total > MAX_BYTES:
                    raise ProbeError
                frame = json.loads(line)
                if not isinstance(frame, dict):
                    raise ProbeError
                while not stop.is_set():
                    try:
                        frames.put(frame, timeout=.05)
                        break
                    except queue.Full:
                        continue
        except (ValueError, OSError, RecursionError, ProbeError):
            while not stop.is_set():
                try:
                    frames.put(None, timeout=.05)
                    break
                except queue.Full:
                    continue

    def send(message):
        if jsonrpc:
            message['jsonrpc'] = '2.0'
        process.stdin.write((json.dumps(message) + '\n').encode())
        process.stdin.flush()

    def response(identifier):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeError
            try:
                frame = frames.get(timeout=remaining)
            except queue.Empty:
                raise ProbeError from None
            if frame is None:
                raise ProbeError
            if frame.get('id') == identifier and not isinstance(frame.get('id'), bool):
                if 'error' in frame or not isinstance(frame.get('result'), dict):
                    raise ProbeError
                return frame['result']

    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=env,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        reader = threading.Thread(target=read_frames, daemon=True)
        reader.start()
        params = {'clientInfo': {'name': 'agent_toolkit_usage', 'version': '1.0'}}
        if jsonrpc:
            params['capabilities'] = {'userInputDialogs': False}
        send({'id': 1, 'method': 'initialize', 'params': params})
        response(1)
        send({'method': 'initialized'})
        request = {'id': 2, 'method': method}
        if not jsonrpc:
            request['params'] = {}
        send(request)
        return response(2)
    except (OSError, ValueError, ProbeError):
        raise ProbeError from None
    finally:
        stop.set()
        if process is not None:
            close_process(process, reader)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects before a bearer token can reach another endpoint."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError('', code, 'redirect_rejected', {}, None)


def claude_version():
    try:
        # Bound version output without persistent files.
        process = subprocess.Popen([command_path('claude'), '--version'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except (OSError, ProbeError):
        return 'unknown'
    output = queue.Queue(maxsize=1)
    reader = threading.Thread(target=lambda: output.put(process.stdout.read(256)), daemon=True)
    reader.start()
    try:
        raw = output.get(timeout=2).decode('utf-8', errors='replace')
        match = re.match(r'([0-9]+\.[0-9]+\.[0-9]+)\b', raw)
        return match.group(1) if match else 'unknown'
    except queue.Empty:
        return 'unknown'
    finally:
        close_process(process, reader)


def read_http_body(response):
    """Bound the body size and reject body reads after the elapsed deadline."""
    deadline = time.monotonic() + RPC_TIMEOUT
    body = bytearray()
    while True:
        if time.monotonic() >= deadline:
            raise ProbeError
        # read1 uses at most one underlying read, unlike read's fill loop.
        chunk = response.read1(min(65536, MAX_BYTES + 1 - len(body)))
        if time.monotonic() >= deadline:
            raise ProbeError
        body.extend(chunk)
        if len(body) > MAX_BYTES:
            raise ProbeError
        if not chunk:
            return bytes(body)


def probe_claude(now=None):
    try:
        path = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'))) / '.credentials.json'
        with path.open('rb') as stream:
            body = stream.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            return unknown('claude', 'credentials_invalid')
        token = json.loads(body)['claudeAiOauth']['accessToken']
        if not isinstance(token, str) or not token or not token.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in token):
            return unknown('claude', 'credentials_invalid')
        request = urllib.request.Request('https://api.anthropic.com/api/oauth/usage',
                                         headers={'Authorization': 'Bearer ' + token,
                                                  'anthropic-beta': 'oauth-2025-04-20',
                                                  'User-Agent': f'claude-cli/{claude_version()} (external, cli)'})
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            body = read_http_body(response)
        return normalize_claude(json.loads(body), time.time() if now is None else now)
    except urllib.error.HTTPError as error:
        reason = {401: 'authentication_required', 429: 'usage_read_throttled'}.get(error.code, 'http_error')
        return unknown('claude', reason)
    except FileNotFoundError:
        return unknown('claude', 'credentials_missing')
    except (OSError, ValueError, KeyError, TypeError, RecursionError, http.client.HTTPException, ProbeError):
        return unknown('claude', 'usage_read_failed')


def probe(provider):
    try:
        if provider == 'claude':
            return probe_claude()
        if provider == 'codex':
            raw = rpc_read([command_path('codex'), 'app-server', '--listen', 'stdio://'], 'account/rateLimits/read')
            return normalize_codex(raw, time.time())
        raw = rpc_read([command_path('muse'), 'serve', '--no-session-log', '--disable-write', '--disable-shell'],
                       'usage/read', True,
                       env=dict(os.environ, MUSE_NO_AUTO_UPDATE='1', MUSE_LOGIN='0'))
        return normalize_muse(raw, time.time())
    except Exception:
        # A provider boundary must never suppress another provider's report.
        return unknown(provider, 'usage_read_failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=tuple(SOURCES))
    args = parser.parse_args()
    selected = [args.provider] if args.provider else list(SOURCES)
    providers = {name: unknown(name, 'not_requested') for name in SOURCES}
    with ThreadPoolExecutor(max_workers=len(selected)) as pool:
        for name, result in zip(selected, pool.map(probe, selected)):
            providers[name] = result
    print(json.dumps({'observed_at': utc(time.time()), 'providers': providers}, allow_nan=False))


if __name__ == '__main__':
    main()
