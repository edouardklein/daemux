"""Daemux lets you run daemons in a tmux pane.

That way, you wan write programs that launch long-running background
tasks, and check these tasks' health by hand, relaunch them, etc. by
attaching to the corresponding pane in tmux.

Daemux depends on Python, tmux, and libtmux.

>>> import daemux
>>> # session, window, and pane are implicitely deduced if
>>> # not explicitely specified
>>> yes = daemux.start('yes')
>>> yes.status()
'running'
>>> # One can reattach from somewhere else
>>> yes2 = daemux.reattach(session='yes', window='yes', pane=-1)
>>> yes2.status()
'running'
>>> # Reattaching gives full control
>>> yes2.stop()
>>> yes2.status()
'ready'
>>> # Control is still available from the original instance
>>> yes.status()
'ready'
>>> yes.start()
>>> yes2.status()
'running'
>>> yes.stop()
"""

import os
import shlex
import shutil
import subprocess
import time

import libtmux

__version__ = '0.1.2'


def _get_session(server, session_name):
    """Return a session by name or ``None`` if it does not exist."""
    return server.sessions.get(default=None, session_name=session_name)


def _get_window(session, window_name):
    """Return a window by name or ``None`` if it does not exist."""
    return session.windows.get(default=None, window_name=window_name)


def _sorted_panes(window):
    """Return panes ordered by tmux pane index."""
    return sorted(window.panes, key=lambda pane: int(pane.pane_index))


def _pane_tty_names(pane_tty):
    """Return tty names to try with ``ps -t`` in portability order."""
    tty = pane_tty.removeprefix('/dev/')
    if tty == pane_tty:
        return [tty]
    return [tty, pane_tty]


def _sync_environment(session, environment):
    """Update tmux session environment from the caller environment."""
    for name, value in environment.items():
        session.set_environment(name, value)


def _command_with_env(cmd, environment):
    """Return a shell command that launches ``cmd`` with an exact environment.
    """
    env_binary = shutil.which('env') or 'env'
    sh_binary = shutil.which('sh') or 'sh'
    command = [env_binary, '-i']
    command.extend(f'{name}={value}'
                   for name, value in sorted(environment.items()))
    command.extend([sh_binary, '-lc', f'exec {cmd}'])
    return ' '.join(shlex.quote(part) for part in command)


class Daemon:
    """Handle tmux session, window and pane to control the daemon."""

    def __init__(self, cmd, session=None, window=None, pane=None, layout=None,
                 env=None):
        """Create or attach to a session/window/pane for command cmd.

        Args:
            cmd: The command to run to start the daemon.

            session: The name of the tmux session in which to
                run the daemon. Derived from `cmd` if None.
                Will be created if it does not already exists.

            window: The name of the tmux window (inside of `session`)
                in which to run the daemon. Derived frm `cmd` if None.
                Will be created if it does not already exists.

            pane: The number of the pane (inside of `window`) in which
                to run the daemon. A new pane will be created if None.
                As many panes as necessary will be created so that
                pane number `pane` exists. Python indexes work, so
                asking for pane e.g. -1 makes sense.

            layout: The layout to apply after each pane creation. Defaults
                to None, in which case no layout is applied. Creating too many
                panes will eventually make tmux fail, complaining that there
                is not enough space left to create a new pane. Using the e.g.
                'tiled' layout is a good way to delay this problem.

            env: Exact environment mapping to use when launching `cmd`.
                If None, the daemon is launched through the pane shell as-is.
        """
        self.cmd = cmd
        self.env = dict(env) if env is not None else None
        if window is not None and session is None:
            raise ValueError("If window is set, session should be set.")
        if pane is not None and (window is None or session is None):
            raise ValueError('If pane is set, '
                             'window and session should be set.')
        if session is None:
            session = cmd.split()[0]
        if window is None:
            window = cmd.split()[0]

        self.server = libtmux.Server()
        self.environment = dict(os.environ)

        self.session = _get_session(self.server, session)
        if not self.session:
            self.session = self.server.new_session(
                session_name=session,
                attach=False,
                window_name=window,
                environment=self.environment,
            )
        _sync_environment(self.session, self.environment)

        self.window = _get_window(self.session, window)
        if not self.window:
            self.window = self.session.new_window(window_name=window,
                                                  attach=False,
                                                  environment=self.environment)
            if pane is not None and pane != 0:
                raise ValueError('pane was specified as {}, but window {}'
                                 ' did not exist (it does now). Legal values'
                                 'of pane were therefore only 0 '
                                 'and None.'.format(pane, window))
            if pane is None:
                pane = 0  # So that we wont split the window we just created

        if pane is None:  # Creation of a new pane
            self.pane = self.window.split(attach=False,
                                          environment=self.environment)
            if layout is not None:
                self.window.select_layout(layout)
        else:
            while max(-pane - 1, pane) >= len(self.window.panes):
                # Create as many panes as necessary to honor request
                self.window.split(attach=False,
                                  environment=self.environment)
                if layout is not None:
                    self.window.select_layout(layout)
            # Pane ordering can change after layout changes.
            # Tmux pane indexes recover the requested pane.
            self.pane = _sorted_panes(self.window)[pane]

        if cmd is not None:
            if 'daemux ready to run daemon ' in self.pane_output():
                pane_index = int(self.pane.pane_index)
                self.pane.cmd('respawn-pane', '-k')
                self.pane = _sorted_panes(self.window)[pane_index]
            self.pane.send_keys("# Pane {},"
                                "daemux ready to run daemon"
                                " {}".format(self.pane, self.cmd))

    def pane_ps(self):
        """Return the ps output for processes running in our pane."""
        errors = []
        for tty in _pane_tty_names(self.pane.pane_tty):
            try:
                return subprocess.check_output(['ps', '-t', tty],
                                               stderr=subprocess.STDOUT)\
                    .decode('utf8')
            except subprocess.CalledProcessError as exc:
                errors.append(exc)
        raise errors[-1]

    def pane_output(self):
        """Return the contents of the pane."""
        # FIXME: -32000 should be changed when tmux v2 becomes widely
        # available to just '-', meaning 'all history'.
        return '\n'.join(self.pane.cmd('capture-pane', '-p',
                                       '-S', '-32000').stdout)

    def status(self):
        """Return the putative status of the daemon.

        Return:
             'running' if more than one process appear to be running in
             the daemon's pane's tty
             'ready' if only one process is running in the daemon's pane's tty
        """
        # There is a header line
        nb_processes = len(self.pane_ps().strip().split('\n')) - 1
        if nb_processes > 1:
            return 'running'
        assert nb_processes == 1, '''ps output is not as expected:
        {}'''.format(self.pane_ps())
        return 'ready'

    def restart(self, timeout=10):
        """Relaunch the daemon by sending an arrow up and enter."""
        self.stop()
        self.pane.cmd('send-keys', 'Up')
        self.pane.enter()
        self.wait_for_state('running', timeout=timeout)

    def start(self, timeout=10):
        """Start the daemon."""
        self.wait_for_state('ready', timeout=timeout)
        if self.cmd is None:
            return self.restart()
        command = self.cmd
        if self.env is not None:
            command = _command_with_env(self.cmd, self.env)
        self.pane.send_keys(command)
        self.wait_for_state('running', timeout=timeout)

    def stop(self):
        """Send Ctrl-Cs to the pane the daemon is running on until it stops."""
        self.pane.cmd('send-keys', 'C-c')
        self.wait_for_state(state='ready',
                            action=lambda: self.pane.cmd('send-keys', 'C-c'))

    def wait_for_state(self, state, action=None, timeout=10):
        """Wait (until timeout) for status to change to the specified state
        before returning.
        If action is specified, it is called every second while status is not
        at state.
        """
        _wait_for_condition(lambda: self.status() == state, action, timeout,
                            lambda: RuntimeError("Could not get the daemon {} "
                                                 "to switch to "
                                                 "state {} (timeout)."
                                                 " Current output is:\n{}"
                                                 .format(self.cmd, state,
                                                         self.pane_output())))

    def wait_for_output(self, expected_output, action=None, timeout=10):
        """Wait (until timeout) for expected output to appear on the pane
        before returning.
        If action is specified, it is called every second until the expected
        output appears.
        """
        _wait_for_condition((lambda: expected_output in self.pane_output()),
                            action, timeout,
                            lambda: RuntimeError("Command {} did not launch "
                                                 "properly (timeout).\n"
                                                 .format(self.cmd)))


def start(cmd, **kwargs):
    """Start a new daemon and return it.

    The daemon is created with the arguments given to start.
    See :py:func:`Daemon.__init__` for details.

    One can give an explicit tmux session/window/pane hierarchy:

    >>> import daemux
    >>> d = daemux.start(cmd='yes', session='yes', window='yes', pane=-1)
    >>> d.stop()
    """
    answer = Daemon(cmd, **kwargs)
    answer.start()
    return answer


def _wait_for_condition(condition, action=None, timeout=10,
                        exception=lambda: RuntimeError('Timeout while waiting'
                                                       'for condition')):
    """Wait until timeout for a given condition to be satisfied,
    calling the optional action every second."""
    start_time = time.time()
    while not condition():
        if action is not None:
            action()
        time.sleep(1)
        if time.time() - start_time > timeout:
            raise exception()


def reattach(session, window, pane):
    """Returns the Daemon Object tied to the specified tmux hierarchy."""
    return Daemon(cmd=None, session=session, window=window, pane=pane)


if __name__ == '__main__':
    import doctest
    doctest.testmod()
