"""Daemux lets you run daemons in a tmux pane.

That way, you wan write programs that launch long-running background
tasks, and check these tasks' health by hand, relaunch them, etc. by
attaching to the corresponding pane in tmux.

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

import libtmux
import subprocess
import time

__version__ = '0.1.0'


class Daemon:
    """Handle tmux session, window and pane to control the daemon."""

    def __init__(self, cmd, session=None, window=None, pane=None, layout=None):
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
        """
        self.cmd = cmd
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

        self.session = self.server.find_where({'session_name': session})
        if not self.session:
            self.session = self.server.new_session(session)
            # Rename the implicitely created window so that it can be found
            # on next line
            self.session.list_windows()[0].rename_window(window)

        self.window = self.session.find_where({'window_name': window})
        if not self.window:
            self.window = self.session.new_window(window)
            if pane is not None and pane != 0:
                raise ValueError('pane was specified as {}, but window {}'
                                 ' did not exist (it does now). Legal values'
                                 'of pane were therefore only 0 '
                                 'and None.'.format(pane, window))
            if pane is None:
                pane = 0  # So that we wont split the window we just created

        if pane is None:  # Creation of a new pane
            self.pane = self.window.split_window()
            if layout is not None:
                self.window.select_layout(layout)
        else:
            while max(-pane - 1, pane) >= len(self.window.list_panes()):
                # Create as many panes as necessary to honor request
                self.window.split_window()
                if layout is not None:
                    self.window.select_layout(layout)
            # Sorting because list_panes may not return the panes in the
            # expected order (I expected chronological order),
            # maybe because of the call to select_layout, which changes the
            # order of the panes. We sort str(pane), which contains
            # the pane number, which is always increasing and therefore the
            # same as chronological order.
            self.pane = sorted(self.window.list_panes(), key=str)[pane]

        if cmd is not None:
            if 'daemux ready to run daemon ' in self.pane_output():
                self.pane.cmd('respawn-pane', '-k')
                self.pane = sorted(self.window.list_panes(), key=str)[pane]
            self.pane.send_keys("# Pane {},"
                                "daemux ready to run daemon"
                                " {}".format(self.pane, self.cmd))

    def pane_ps(self):
        """Return the ps output for processes running in our pane."""
        return subprocess.check_output('ps -t {}'
                                       .format(self.pane['pane_tty']),
                                       shell=True).decode('utf8')

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
