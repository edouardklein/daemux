"""Daemux lets you run daemons in a tmux pane.

That way, you can write programs that launch long-running background
tasks, and check these tasks' health by hand, relaunch them, etc. by
attaching to the corresponding pane in tmux.

Daemux depends on Python, tmux, libtmux, and
`s6-envdir <https://skarnet.org/software/s6/s6-envdir.html>`_.

Basic usage
-----------

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
>>> yes.session.kill()

Environment passing
-------------------

By default, daemux does not copy Python's environment into tmux. The
command below prints the day of the week for January 1st 1970 in
whatever locale tmux's shell already has:

>>> import os
>>> d = daemux.start("date -u -d @0 +%A")  # doctest: +SKIP
>>> d.pane_output().splitlines()[-1]  # doctest: +SKIP
'loS jaj'

If you want an exact environment, pass it explicitly with ``env=``.
Here, alternating ``LC_ALL`` alternates between English and French:

>>> os.environ["LC_ALL"] = "en_US.utf8"
>>> d = daemux.start('yes "$(date -u -d @0 +%A)"', env=os.environ)
>>> d.pane_output().splitlines()[-2]
'Thursday'
>>> d.stop()
>>> os.environ["LC_ALL"] = "fr_FR.utf8"
>>> d = daemux.start('yes "$(date -u -d @0 +%A)"', env=os.environ)
>>> d.pane_output().splitlines()[-2]
'jeudi'
>>> d.stop()
>>> d.session.kill()

Commands started with ``env=`` are wrapped in ``sh -c 'exec ...'``
inside that exact environment. This lets shell expansion use the
variables you passed:

>>> env = {"PATH": os.environ["PATH"], "WORD": "maybe"}
>>> d = daemux.start("yes $WORD")
>>> d.pane_output().splitlines()[-1]
'y'
>>> d.stop()

Without ``env=``, daemux just sends the command to tmux's existing
shell, so only that shell's environment matters.

With ``env=``, the wrapped command sees the variables you passed:

>>> d = daemux.start("yes $WORD", env=env)
>>> d.wait_for_output("maybe")
>>> d.pane_output().splitlines()[-1]
'maybe'
>>> d.stop()
>>> d.session.kill()
>>> # env= also honors SHELL. Complex shell snippets should disable the
>>> # wrapper's automatic exec and provide their own exec at the end.
>>> bash = shutil.which("bash")
>>> yes_binary = shutil.which("yes")
>>> d = daemux.start(f'a=(bash); exec {yes_binary} "${{a[0]}}"',
...                   env={"SHELL": bash},
...                   exec=False)
>>> d.pane_output().splitlines()[-2]
'bash'
>>> d.stop()
>>> d.session.kill()
"""

import os
import shlex
import shutil
import subprocess
import tempfile
import time

import libtmux

__version__ = '0.2.3'


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


def _sanitize_tmux_name(name):
    """Return a tmux-safe name derived from a command token."""
    allowed = set('abcdefghijklmnopqrstuvwxyz'
                  'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                  '0123456789'
                  '-_')
    sanitized = ''.join(char for char in name if char in allowed)
    return sanitized or 'daemon'


def _derived_tmux_name(cmd):
    """Return the default tmux session/window name for ``cmd``."""
    return _sanitize_tmux_name(cmd.split()[0])


def _wrapped_command(cmd, sh_binary='/bin/sh', do_exec=True):
    """Return a shell-wrapped command string."""
    if do_exec:
        cmd = f'exec {cmd}'
    return ' '.join(shlex.quote(part) for part in [sh_binary,
                                                   '-c',
                                                   cmd])


def _write_envdir(path, environment):
    """Write ``environment`` to ``path`` for ``s6-envdir -f -L``."""
    os.makedirs(path, exist_ok=True)
    names = set()
    for name, value in sorted(environment.items()):
        name = str(name)
        value = str(value)
        if not name or name.startswith('.') or '/' in name or '=' in name:
            raise ValueError(
                f'Unsupported environment variable name: {name!r}'
            )
        names.add(name)
        with open(os.path.join(path, name), 'w', encoding='utf-8') as handle:
            handle.write(value)
            # s6-envdir -f strips one final newline, so we add one sentinel
            # newline to round-trip arbitrary values exactly.
            handle.write('\n')
    for name in os.listdir(path):
        file_path = os.path.join(path, name)
        if os.path.isfile(file_path) and name not in names:
            os.remove(file_path)


def _command_with_env(cmd, envdir_path):
    """Return a command that loads an exact environment via ``s6-envdir``."""
    env_binary = shutil.which('env') or 'env'
    s6_envdir_binary = shutil.which('s6-envdir')
    if s6_envdir_binary is None:
        raise RuntimeError('env= requires s6-envdir to be installed.')
    command = [env_binary, '-i', s6_envdir_binary, '-f', '-L', envdir_path]
    return '{} {}'.format(' '.join(shlex.quote(part) for part in command), cmd)


def _new_envdir(environment):
    """Create and populate a fresh envdir snapshot."""
    path = tempfile.mkdtemp(prefix='daemux-envdir-')
    _write_envdir(path, environment)
    return path


class Daemon:
    """Handle tmux session, window and pane to control the daemon."""

    def __init__(self, cmd, session=None, window=None, pane=None, layout=None,
                 env=None, exec=True, _wrapped_env=False):
        """Create or attach to a session/window/pane for command cmd.

        Args:
            cmd: The command to run to start the daemon.

            session: The name of the tmux session in which to
                run the daemon. Derived from `cmd` if None.
                Will be created if it does not already exists.

            window: The name of the tmux window (inside of `session`)
                in which to run the daemon. Derived from `cmd` if None.
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

            exec: Whether daemux should prepend ``exec`` inside the shell
                wrapper it uses for ``env=`` launches. Set to False for
                complex shell snippets that provide their own final exec.
        """
        if window is not None and session is None:
            raise ValueError("If window is set, session should be set.")
        if pane is not None and (window is None or session is None):
            raise ValueError('If pane is set, '
                             'window and session should be set.')
        if cmd is not None:
            if session is None:
                session = _derived_tmux_name(cmd)
            if window is None:
                window = _derived_tmux_name(cmd)

        if cmd is not None and env is not None:
            shell_binary = env.get('SHELL', '/bin/sh')
            self.__init__(_command_with_env(_wrapped_command(cmd,
                                                             sh_binary=shell_binary,
                                                             do_exec=exec),
                                            _new_envdir(env)),
                          session=session,
                          window=window,
                          pane=pane,
                          layout=layout,
                          env=None,
                          _wrapped_env=True)
            return

        self.cmd = cmd
        self.env = None
        self._wrapped_env = _wrapped_env

        self.server = libtmux.Server()

        self.session = _get_session(self.server, session)
        if not self.session:
            self.session = self.server.new_session(
                session_name=session,
                attach=False,
                window_name=window,
            )

        self.window = _get_window(self.session, window)
        if not self.window:
            self.window = self.session.new_window(window_name=window,
                                                  attach=False)
            if pane is not None and pane != 0:
                raise ValueError('pane was specified as {}, but window {}'
                                 ' did not exist (it does now). Legal values'
                                 'of pane were therefore only 0 '
                                 'and None.'.format(pane, window))
            if pane is None:
                pane = 0  # So that we wont split the window we just created

        if pane is None:  # Creation of a new pane
            self.pane = self.window.split(attach=False)
            if layout is not None:
                self.window.select_layout(layout)
        else:
            while max(-pane - 1, pane) >= len(self.window.panes):
                # Create as many panes as necessary to honor request
                self.window.split(attach=False)
                if layout is not None:
                    self.window.select_layout(layout)
            # Pane ordering can change after layout changes.
            # Tmux pane indexes recover the requested pane.
            self.pane = _sorted_panes(self.window)[pane]

        self._shell_command = self._pane_current_command()

        if cmd is not None:
            if 'daemux ready to run daemon ' in self.pane_output():
                pane_index = int(self.pane.pane_index)
                self.pane.cmd('respawn-pane', '-k')
                self.pane = _sorted_panes(self.window)[pane_index]
                self._shell_command = self._pane_current_command()
            self.pane.send_keys("# Pane {},"
                                "daemux ready to run daemon"
                                " {}".format(self.pane, self.cmd))

    def _pane_current_command(self):
        """Return tmux's view of the pane foreground command.

        This is not the full process list for the pane tty. It is tmux's own
        ``#{pane_current_command}`` value, which briefly stays at the pane
        shell while an ``env=``-wrapped launcher is still being echoed and
        handed off to the real daemon.
        """
        current = self.pane.cmd('display-message', '-p',
                                '#{pane_current_command}').stdout
        return current[0] if current else ''

    def _wrapped_launcher_pending(self, nb_processes):
        """Return whether an ``env=`` launch is still in tmux's shell phase.

        With ``env=``, daemux sends a wrapped command of the form
        ``env -i s6-envdir ... sh -c 'exec ...'``. There is a short interval
        where ``ps -t`` already shows two processes on the pane tty, but tmux
        still reports the pane foreground command as the original interactive
        shell and the last visible pane line is only the echoed launcher.

        During that interval, reporting ``running`` is too early for callers
        that expect the command's own output to be visible as soon as
        ``start()`` returns.
        """
        if not self._wrapped_env:
            return False
        # The race we are compensating for only showed up for the simple
        # two-process case: pane shell + final daemon.
        if nb_processes != 2:
            return False
        # Once tmux sees a foreground command other than the original pane
        # shell, the handoff has completed and we can trust the running state.
        if self._pane_current_command() != self._shell_command:
            return False
        lines = self.pane_output().splitlines()
        if not lines:
            return False
        # While the last visible line is still just a fragment of the launcher
        # we sent, the daemon has not produced user-visible output yet.
        return lines[-1] in self.cmd

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
        return '\n'.join(self.pane.cmd('capture-pane', '-p',
                                       '-S', '-').stdout)

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
            if self._wrapped_launcher_pending(nb_processes):
                return 'ready'
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
        self.pane.send_keys(self.cmd)
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
    >>> d = daemux.start(cmd='yes', session='yes-start', window='yes', pane=0)
    >>> d.stop()
    >>> d.session.kill()
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
