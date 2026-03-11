#######
Daemux
#######

Overview
---------

Daemux uses tmux to let you start, stop, restart and check daemons.

Installation
==============

To install from PyPI:

.. code-block:: sh

    python3 -m pip install daemux


Or clone the repo:

.. code-block:: sh

    git clone https://github.com/edouardklein/daemux
    cd daemux
    python3 -m pip install .

Usage
=======

Documentation
++++++++++++++

Read the documentation https://daemux.readthedocs.io/ to understand how to use daemux.

In the cloned repo
+++++++++++++++++++++

For a reproducible Guix environment with the current supported dependency set:

.. code-block:: sh

    guix shell python python-libtmux python-pytest python-coverage python-sphinx python-flake8 tmux -- make test

Helper targets
>>>>>>>>>>>>>>>>

To build the documentation, run:

.. code-block:: sh

    make doc
    
To run the test, run:

.. code-block:: sh

    make test

To check the code's superficial cleanliness run:

.. code-block:: sh

    make lint

Dev cycle
>>>>>>>>>>>

One branch derived from latest master per new feature or bug fix.

When this branch is complete:
- Merge master back in it
        
        $ git merge master
        
- Make sure all tests pass, the code is clean and the doc compiles:

        $ make
        
- Bump the version appropriately (no tags):

        $ bumpversion (major|minor|patch) --commit --no-tag
        
- Rebase everything in order to make one commit (if more are needed, talk the the maintainer). To avoid catastrophic failure, create another branch that won't be rebased first. Keep bumpversion's commit message somewhere in the rebased commit message, but not always on the first line.

        $ git branch <my_feature>_no_rebase

        $ git rebase -i master
        
- Make a pull request, or, if you are the maintainer, switch to master

        $ git checkout master
        
- If you are the maintainer, merge the feature branch:
        
        $ git merge <my_feature>
        
- If you are the maintainer, make sure everything works as it should

- If you are the maintainer, close the relevent issues (by adding fix... in the commit message with --amend)

- If you are the maintainer, create the appropriate tag

        $ git tag <version>

- If you are the maintainer, push the code to any relevant remote

        $ git push
        
- If you are the maintainer, upload the code to PyPI

       $ python3 -m build

       $ twine upload dist/* --skip-existing
        
- If you are the maintainer, check that the docs are updated <http://daemux.readthedocs.io/en/latest/>

- If you are the maintainer or the devops guy, deploy the new code to all relevant machines
