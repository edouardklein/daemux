import uuid

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
