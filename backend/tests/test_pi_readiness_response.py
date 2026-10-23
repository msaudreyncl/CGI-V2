"""Readiness must return JSON even when configuration or a probe fails."""
import configparser
import json
from pathlib import Path
import sys
import threading
from urllib.request import urlopen
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'pi_node'))
import pi_server


@pytest.mark.parametrize('failure', ['config', 'camera', 'none'])
def test_readiness_response(monkeypatch, failure):
    cfg = configparser.ConfigParser()
    cfg.read_dict({'hardware': {'MODE': 'simulation'}})
    def load():
        if failure == 'config':
            raise configparser.Error('Invalid Pi configuration')
        return cfg
    def camera():
        if failure == 'camera':
            raise RuntimeError('Camera probe failed')
        return 'ready'
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'simulation')
    monkeypatch.setattr(pi_server, '_load_config', load)
    monkeypatch.setattr(pi_server, '_camera_readiness', camera)
    monkeypatch.setattr(pi_server, '_read_weight', lambda: (350.0, True, True))
    monkeypatch.setattr(pi_server, '_camera_error', None)
    server = pi_server.ThreadingHTTPServer(('127.0.0.1', 0), pi_server.PiRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            response = urlopen(f'http://127.0.0.1:{server.server_port}/weight', timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            payload = json.load(response)
            assert response.code == (200 if failure == 'none' else 503)
            assert payload['scale'] == ('ready' if failure == 'none' else 'error')
            assert payload['camera'] == ('ready' if failure == 'none' else 'error')
            if failure != 'none':
                assert payload['error']
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
