'''Daemux lets you run daemons in a tmux pane.

That way, you wan write programs that launch long-running background
tasks, and check these tasks' health by hand, relaunch them, etc. by
attaching to the corresponding pane in tmux.

>>> import daemux
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
'''

import libtmux
import subprocess
import time

__version__ = '0.0.5'


class Daemon:
    """Handle tmux session, window and pane to control the daemon."""

    def __init__(self, cmd, session=None, window=None, pane=None):
        '''Create or attach to a session/window/pane for command cmd.

        Args:
            cmd: The command to run to start the daemon
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
        '''
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
        else:
            while max(-pane - 1, pane) >= len(self.window.list_panes()):
                # Create as many panes as necessary to honor request
                self.window.split_window()
            self.pane = self.window.list_panes()[pane]

        if cmd is not None:
            self.pane.send_keys("# Pane {},"
                                " ready to run daemon {}".format(self.pane,
                                                                 self.cmd))

    def pane_ps(self):
        '''Return the ps output for processes running in our pane.'''
        return subprocess.check_output('ps -t {}'
                                       .format(self.pane['pane_tty']),
                                       shell=True).decode('utf8')

    def status(self):
        '''Return the putative status of the daemon.

        Return:
             'running' if more than one process appear to be running in
             the daemon's pane's tty
             'ready' if only one process is running in the daemon's pane's tty
        '''
        # There is a header line
        nb_processes = len(self.pane_ps().strip().split('\n')) - 1
        if nb_processes > 1:
            return 'running'
        assert nb_processes == 1, '''ps output is not as expected:
        {}'''.format(self.pane_ps())
        return 'ready'

    def restart(self, timeout=10):
        """Relaunch the daemon by sending an arrow up and enter."""
        self.pane.cmd('send-keys', 'Up')
        self.pane.enter()
        self.wait_for_running(timeout)

    def start(self, timeout=10):
        """Start the daemon."""
        if self.status() == 'running':
            raise RuntimeError('The shell is not ready to launch our daemon.\n'
                               'Existing processes:\n'
                               '{}'.format(self.pane_ps()))
        if self.cmd is None:
            return self.restart()

        self.pane.send_keys(self.cmd)
        self.wait_for_running(timeout)

    def wait_for_running(self, timeout):
        # Wait for timeout or for status to change before returning
        start = time.time()
        while self.status() == 'ready':
            time.sleep(1)
            if time.time() - start > timeout:
                raise RuntimeError("Could not get the daemon to launch."
                                   " Current output is:\n{}"
                                   .format(self.pane_output()))

    def stop(self):
        '''Send a Ctrl-C to the pane the daemon is running on.'''
        self.pane.cmd('send-keys', 'C-c')


def start(cmd):
    '''Start a new daemon.'''
    answer = Daemon(cmd)
    answer.start()
    return answer


def reattach(session, window, pane):
    '''Return the Daemon Object tied to the specified tmux hierarchy.'''
    return Daemon(cmd=None, session=session, window=window, pane=pane)


if __name__ == '__main__':
    import doctest
    doctest.testmod()
