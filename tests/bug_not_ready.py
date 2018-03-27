#!/usr/bin/env python3
# See issue #2 on the internal GitLab.
# The issue arises when the shell initialization takes too long:
# The state is left at 'running' when start is called()
# It should be 'ready' some time later, but the bug was triggered because
# start() did not wait.
# I replaced a simple status check with a call to wait_for_state()
# which mitigates the problem in all real life cases and
# gives a much more explicit error message should a user have
# a long running process in their .bashrc or such.
# To make the bug appear, pollute your shell initialization
# with a long running process, e.g. for fish:
# for i in (seq 10); echo $i;sleep 1; end
# and run this file.
# This test is not run in an automated fashion
# because the test setup is too cumbersome to automate
# and I'm fairly confident in my bugfix.
# This file is included in version control should one have
# the need to test for a regression sometime in the future.
import daemux

d = daemux.Daemon("yes", session="daemux_test")
d.start()
d.stop()
