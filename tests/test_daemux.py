import os
import shutil
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import libtmux

import daemux


def _kill_session(session_name):
    session = libtmux.Server().sessions.get(default=None,
                                            session_name=session_name)
    if session is not None:
        session.kill()


def test_start_stop_reattach_and_restart():
    session_name = f"daemux-test-{uuid.uuid4().hex[:8]}"
    try:
        daemon = daemux.start("sleep 30",
                              session=session_name,
                              window="main",
                              pane=0)
        assert daemon.status() == "running"

        attached = daemux.reattach(session=session_name, window="main", pane=0)
        assert attached.status() == "running"

        attached.stop()
        assert daemon.status() == "ready"

        daemon.start()
        assert attached.status() == "running"

        daemon.restart()
        assert daemon.status() == "running"

        daemon.stop()
        assert daemon.status() == "ready"
    finally:
        _kill_session(session_name)


def test_reuses_existing_ready_pane():
    session_name = f"daemux-test-{uuid.uuid4().hex[:8]}"
    try:
        first = daemux.Daemon("sleep 30",
                              session=session_name,
                              window="main",
                              pane=0)
        assert first.status() == "ready"

        second = daemux.Daemon("sleep 30",
                               session=session_name,
                               window="main",
                               pane=0)
        assert second.status() == "ready"

        second.start()
        assert second.status() == "running"

        second.stop()
        assert second.status() == "ready"
    finally:
        _kill_session(session_name)


def test_pane_ps_uses_tty_name_without_dev_prefix(monkeypatch):
    daemon = object.__new__(daemux.Daemon)
    daemon.pane = SimpleNamespace(pane_tty='/dev/pts/7')
    calls = []

    def fake_check_output(cmd, stderr=None):
        calls.append(cmd)
        assert stderr == subprocess.STDOUT
        if cmd == ['ps', '-t', 'pts/7']:
            return b'PID TTY          TIME CMD\n1 pts/7 00:00:00 sh\n'
        raise AssertionError(cmd)

    monkeypatch.setattr(daemux.subprocess, 'check_output', fake_check_output)

    assert 'pts/7' in daemon.pane_ps()
    assert calls == [['ps', '-t', 'pts/7']]


def test_pane_ps_falls_back_to_full_tty_name(monkeypatch):
    daemon = object.__new__(daemux.Daemon)
    daemon.pane = SimpleNamespace(pane_tty='/dev/pts/8')
    calls = []

    def fake_check_output(cmd, stderr=None):
        calls.append(cmd)
        assert stderr == subprocess.STDOUT
        if cmd == ['ps', '-t', 'pts/8']:
            raise subprocess.CalledProcessError(1, cmd, output=b'bad tty\n')
        if cmd == ['ps', '-t', '/dev/pts/8']:
            return b'PID TTY          TIME CMD\n1 pts/8 00:00:00 sh\n'
        raise AssertionError(cmd)

    monkeypatch.setattr(daemux.subprocess, 'check_output', fake_check_output)

    assert 'pts/8' in daemon.pane_ps()
    assert calls == [['ps', '-t', 'pts/8'], ['ps', '-t', '/dev/pts/8']]


def test_start_env_survives_interactive_bash_resetting_path(
        monkeypatch,
        tmp_path):
    socket_name = f"daemux-env-{uuid.uuid4().hex[:8]}"
    session_name = f"daemux-test-env-{uuid.uuid4().hex[:8]}"
    bash = shutil.which('bash')
    shell = shutil.which('sh')
    assert bash is not None
    assert shell is not None

    stale_bin = Path(tmp_path) / 'stale-bin'
    stale_bin.mkdir()
    home = Path(tmp_path) / 'home'
    home.mkdir()
    probe_output = Path(tmp_path) / 'probe-output'
    probe = Path(tmp_path) / 'probe-script'
    probe.write_text(
        f'#!{shell}\nprintf success > "$PROBE_OUTPUT"\nsleep 30\n',
        encoding='utf-8',
    )
    probe.chmod(0o755)
    (home / '.bashrc').write_text(f'export PATH={stale_bin}\n',
                                  encoding='utf-8')

    good_env = {
        'HOME': str(home),
        'PATH': f'{tmp_path}:{os.environ["PATH"]}',
        'PROBE_OUTPUT': str(probe_output),
    }

    original_server = libtmux.Server
    server = original_server(socket_name=socket_name)

    def server_factory(*args, **kwargs):
        kwargs.setdefault('socket_name', socket_name)
        return original_server(*args, **kwargs)

    monkeypatch.setattr(daemux.libtmux, 'Server', server_factory)
    monkeypatch.setenv('HOME', str(home))
    server.cmd('set-option', '-g', 'default-command', f'exec {bash} -i')

    try:
        daemon = daemux.Daemon('probe-script',
                               session=session_name,
                               window='main',
                               pane=0,
                               env=good_env)
        daemon.start()
        daemux._wait_for_condition(
            probe_output.exists,
            timeout=10,
            exception=lambda: RuntimeError('probe-script did not run'),
        )
        assert probe_output.read_text(encoding='utf-8') == 'success'
        assert daemon.status() == 'running'
        daemon.stop()
        assert daemon.status() == 'ready'
    finally:
        session = original_server(socket_name=socket_name).sessions.get(
            default=None,
            session_name=session_name,
        )
        if session is not None:
            session.kill()
        server.cmd('kill-server')
