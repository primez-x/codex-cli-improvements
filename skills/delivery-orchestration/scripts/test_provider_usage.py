"""Fixture-only checks. Run: python3 -B test_provider_usage.py.

Failure modes: bad percentages, expired resets, incomplete shared windows,
stale Muse data, scoped-only quotas, blocked flags, secret disclosure,
malformed/large RPC frames, EOF, timeout, handshake order, notification noise,
missing executables, missing credentials, unsafe tokens, redirects, HTTP errors,
large HTTP bodies, and owned process cleanup.
"""
import contextlib
import importlib.util
import io
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error

SCRIPT = Path(__file__).with_name('provider_usage.py')
NOW = 1800000000


def module():
    spec = importlib.util.spec_from_file_location('provider_usage', SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def window(used=14, reset=NOW + 3600):
    return {'usedPercent': used, 'windowDurationMins': 10080, 'resetsAt': reset}


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'collector is absent')
        self.m = module()

    def test_codex_shared_and_scoped(self):
        data = {'ordinaryUsageAllowed': True, 'rateLimits': {'primary': window()},
                'rateLimitsByLimitId': {'private-account': {
                    'normalModelSlug': 'gpt-6', 'primary': window(99)}}}
        result = self.m.normalize_codex(data, NOW)
        self.assertEqual(result['headroom_percent'], 86)
        self.assertEqual(result['status'], 'available')
        self.assertEqual([w['scope'] for w in result['windows']], ['shared', 'model'])
        self.assertNotIn('private-account', json.dumps(result))

    def test_bad_windows_never_create_headroom(self):
        for value in [True, -1, float('nan'), float('inf'), '14']:
            with self.subTest(value=value):
                result = self.m.normalize_codex({'rateLimits': {'primary': window(value)}}, NOW)
                self.assertEqual(result['status'], 'unknown')
                self.assertNotIn('headroom_percent', result)
        for reset in [NOW, NOW - 1, None, True, 'bad']:
            result = self.m.normalize_codex({'rateLimits': {'primary': window(reset=reset)}}, NOW)
            self.assertEqual(result['status'], 'unknown')
        data = {'rateLimits': {'primary': window(), 'secondary': window(-1)}}
        self.assertEqual(self.m.normalize_codex(data, NOW)['status'], 'unknown')

    def test_blocked_flags_and_exhaustion(self):
        for data in [{'ordinaryUsageAllowed': False}, {'rateLimits': {'spendControlReached': True}},
                     {'rateLimits': {'primary': window(101)}}]:
            result = self.m.normalize_codex(data, NOW)
            self.assertEqual(result['status'], 'blocked')
        result = self.m.normalize_codex({'rateLimits': {'primary': window(101)}}, NOW)
        self.assertEqual(result['headroom_percent'], 0)

    def test_blocked_flag_overrides_positive_windows(self):
        result = self.m.normalize_codex({'ordinaryUsageAllowed': False,
                                        'rateLimits': {'primary': window()}}, NOW)
        self.assertEqual(result['headroom_percent'], 0)

    def test_current_model_scope_names(self):
        for model in ['gpt-6.1-sol', 'gpt-6-luna', 'gpt-6-astra']:
            self.assertEqual(self.m.model_family(model), model)
        self.assertEqual(self.m.model_family('Claude Fable 5.1'), 'claude-fable')

    def test_extreme_observation_timestamp_is_unknown(self):
        result = self.m.normalize_muse({'usage': {'observedAtMs': 10 ** 400}}, NOW)
        self.assertEqual(result['status'], 'unknown')

    def test_muse_absence_staleness_and_freshness(self):
        self.assertEqual(self.m.normalize_muse({}, NOW)['status'], 'unknown')
        usage = {'observedAtMs': (NOW - 301) * 1000,
                 'window': {'usedPercent': 20, 'windowDurationMins': 300,
                            'resetsAtMs': (NOW + 60) * 1000},
                 'weekly': {'usedPercent': 60, 'resetsAtMs': (NOW + 3600) * 1000}}
        self.assertEqual(self.m.normalize_muse({'usage': usage}, NOW)['status'], 'unknown')
        usage['observedAtMs'] = NOW * 1000
        self.assertEqual(self.m.normalize_muse({'usage': usage}, NOW)['headroom_percent'], 40)

    def test_claude_general_precedence_and_scopes(self):
        reset = '2027-01-15T09:00:00Z'
        data = {'five_hour': {'utilization': 52, 'resets_at': reset},
                'seven_day': {'utilization': 69, 'resets_at': reset},
                'limits': [{'kind': 'session', 'percent': 52, 'resets_at': reset},
                           {'kind': 'weekly_scoped', 'percent': 90, 'resets_at': reset,
                            'scope': {'model': {'display_name': 'Claude Sonnet 4.5'}}}],
                'extra_usage': {'secret': 'DO-NOT-EMIT'}}
        result = self.m.normalize_claude(data, NOW)
        self.assertEqual(result['headroom_percent'], 31)
        self.assertEqual(len(result['windows']), 3)
        self.assertNotIn('DO-NOT-EMIT', json.dumps(result))
        del data['five_hour']
        del data['seven_day']
        data['limits'] = data['limits'][1:]
        self.assertEqual(self.m.normalize_claude(data, NOW)['status'], 'unknown')

    def test_claude_limits_percent_format(self):
        data = {'limits': [{'kind': kind, 'percent': used, 'resets_at': NOW + 3600}
                           for kind, used in [('session', 52), ('weekly_all', 69)]]}
        self.assertEqual(self.m.normalize_claude(data, NOW)['headroom_percent'], 31)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'collector is absent')
        self.m = module()

    def rpc_fixture(self, tail, protocol=False, timeout=2):
        code = '''import json,sys,time
first=json.loads(sys.stdin.readline())
assert first['method']=='initialize' and first['id']==1
print(json.dumps({'id':1,'result':{}}),flush=True)
notification=json.loads(sys.stdin.readline())
assert notification['method']=='initialized'
request=json.loads(sys.stdin.readline())
assert request['id']==2
'''
        if protocol:
            code += "assert notification['jsonrpc']=='2.0' and 'params' not in request\n"
        return self.m.rpc_read([sys.executable, '-u', '-c', code + tail],
                               'usage/read' if protocol else 'account/rateLimits/read',
                               protocol, timeout)

    def test_handshake_noise_and_cleanup(self):
        for protocol in [False, True]:
            data = self.rpc_fixture("print('{\"method\":\"noise\"}',flush=True)\n"
                                    "print('{\"id\":2,\"result\":{\"safe\":true}}',flush=True)\n"
                                    "time.sleep(30)\n", protocol)
            self.assertEqual(data, {'safe': True})

    def test_owned_process_reaped(self):
        original = self.m.subprocess.Popen
        owned = []

        def start(*args, **kwargs):
            process = original(*args, **kwargs)
            owned.append(process)
            return process

        with patch.object(self.m.subprocess, 'Popen', side_effect=start):
            self.rpc_fixture("print('{\"id\":2,\"result\":{}}',flush=True)\ntime.sleep(30)\n")
            with self.assertRaises(self.m.ProbeError):
                self.rpc_fixture('time.sleep(30)', timeout=.1)
        self.assertTrue(all(process.poll() is not None for process in owned))
        self.assertTrue(all(process.stdout.closed and process.stdin.closed for process in owned))

    def test_muse_cli_protocol_and_sanitized_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory, 'muse')
            prefix = ('#!' + sys.executable + '\nimport sys,json\n'
                      'first=json.loads(sys.stdin.readline())\n'
                      'assert first["jsonrpc"]=="2.0"\n'
                      'assert first["params"]["capabilities"]["userInputDialogs"] is False\n'
                      'print(json.dumps({"id":1,"result":{}}),flush=True)\n'
                      'note=json.loads(sys.stdin.readline())\n'
                      'assert note["jsonrpc"]=="2.0"\n'
                      'request=json.loads(sys.stdin.readline())\n'
                      'assert "params" not in request\n')
            for frame in [{'id': 2, 'result': {}},
                          {'id': 2, 'error': {'message': 'fixture-secret'}}]:
                cli.write_text(prefix + 'print(' + repr(json.dumps(frame)) + ',flush=True)\n')
                cli.chmod(0o700)
                run = subprocess.run([sys.executable, '-B', str(SCRIPT), '--provider', 'muse'],
                                     env=dict(os.environ, PATH=directory), capture_output=True,
                                     text=True, timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(json.loads(run.stdout)['providers']['muse']['status'], 'unknown')
                self.assertNotIn('fixture-secret', run.stdout + run.stderr)

    def test_invalid_frames_eof_timeout_and_missing_cli(self):
        for tail in ["print('bad',flush=True)", "print('x'*1048577,flush=True)",
                     "pass", "time.sleep(30)"]:
            start = time.monotonic()
            with self.assertRaises(self.m.ProbeError):
                self.rpc_fixture(tail, timeout=.2)
            self.assertLess(time.monotonic() - start, 2)
        with self.assertRaises(self.m.ProbeError):
            self.m.rpc_read(['/nonexistent/usage-fixture'], 'usage/read', True, .2)

    def test_cli_black_box(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory, 'codex')
            cli.write_text('#!' + sys.executable + '\nimport sys,json\n'
                           'json.loads(sys.stdin.readline())\n'
                           'print(json.dumps({"id":1,"result":{}}),flush=True)\n'
                           'json.loads(sys.stdin.readline());json.loads(sys.stdin.readline())\n'
                           'print(json.dumps({"id":2,"result":{"rateLimits":{"primary":'
                           '{"usedPercent":14,"windowDurationMins":10080,"resetsAt":'
                           + str(time.time() + 3600) + '}}}}),flush=True)\n')
            cli.chmod(0o700)
            env = dict(os.environ, PATH=directory)
            run = subprocess.run([sys.executable, '-B', str(SCRIPT), '--provider', 'codex'],
                                 env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result['providers']['codex']['headroom_percent'], 86)
            self.assertEqual(set(result['providers']), {'codex', 'claude', 'muse'})

    def test_http_body_failure_stays_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, '.credentials.json').write_text(json.dumps(
                {'claudeAiOauth': {'accessToken': 'fixture-secret'}}))
            with patch.dict(os.environ, CLAUDE_CONFIG_DIR=directory), \
                 patch.object(self.m, 'claude_version', return_value='unknown'), \
                 patch.object(self.m.urllib.request, 'build_opener') as opener:
                opener.return_value.open.side_effect = http.client.IncompleteRead(b'fixture-secret')
                result = self.m.probe_claude(NOW)
                self.assertEqual(result['status'], 'unknown')
                self.assertNotIn('fixture-secret', json.dumps(result))

    def test_credentials_boundaries_and_http(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, '.credentials.json')
            with patch.dict(os.environ, CLAUDE_CONFIG_DIR=directory):
                self.assertEqual(self.m.probe_claude(NOW)['status'], 'unknown')
                for token in ['secret\nmalicious', 'secret\rmalicious', True]:
                    path.write_text(json.dumps({'claudeAiOauth': {'accessToken': token}}))
                    with patch.object(self.m.urllib.request, 'build_opener') as opener:
                        self.assertEqual(self.m.probe_claude(NOW)['status'], 'unknown')
                        opener.assert_not_called()
                path.write_text(json.dumps({'claudeAiOauth': {'accessToken': 'fixture-secret'}}))
                for response in [b'bad', b'x' * 1048577, b'{}', b'[' * 50000 + b']' * 50000]:
                    with patch.object(self.m, 'claude_version', return_value='1.2.3'), \
                         patch.object(self.m.urllib.request, 'build_opener') as opener:
                        opener.return_value.open.return_value = contextlib.closing(io.BytesIO(response))
                        result = self.m.probe_claude(NOW)
                        self.assertEqual(result['status'], 'unknown')
                        self.assertNotIn('fixture-secret', json.dumps(result))
                        request = opener.return_value.open.call_args.args[0]
                        self.assertEqual(request.full_url, 'https://api.anthropic.com/api/oauth/usage')
                        self.assertIsNone(request.data)
                payload = {'five_hour': {'utilization': 20, 'resets_at': NOW + 3600},
                           'seven_day': {'utilization': 40, 'resets_at': NOW + 3600}}
                with patch.object(self.m, 'claude_version', return_value='1.2.3'), \
                     patch.object(self.m.urllib.request, 'build_opener') as opener:
                    opener.return_value.open.return_value = contextlib.closing(
                        io.BytesIO(json.dumps(payload).encode()))
                    result = self.m.probe_claude(NOW)
                    self.assertEqual(result['headroom_percent'], 60)
                    request = opener.return_value.open.call_args.args[0]
                    self.assertEqual(request.get_header('User-agent'), 'claude-cli/1.2.3 (external, cli)')
                    self.assertEqual(request.get_header('Anthropic-beta'), 'oauth-2025-04-20')
                    self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-secret')
                for status in [401, 429, 302]:
                    with patch.object(self.m, 'claude_version', return_value='1.2.3'), \
                         patch.object(self.m.urllib.request, 'build_opener') as opener:
                        opener.return_value.open.side_effect = urllib.error.HTTPError(
                            'https://example.com', status, 'fixture-secret', {}, None)
                        result = self.m.probe_claude(NOW)
                        self.assertEqual(result['status'], 'unknown')
                        self.assertNotIn('fixture-secret', json.dumps(result))
                path.write_bytes(b'x' * 1048577)
                self.assertEqual(self.m.probe_claude(NOW)['status'], 'unknown')
        with self.assertRaises(urllib.error.HTTPError):
            self.m.NoRedirect().redirect_request(None, None, 302, 'secret', {}, 'https://example.com')


if __name__ == '__main__':
    unittest.main()
