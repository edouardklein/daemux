#######
Daemux
#######

Overview
---------

Daemux uses tmux to let you start, stop, restart and check daemons.

Installation
==============

To install use pip:

    $ pip3 install daemux


Or clone the repo:

    $ git clone https://github.com/edouardklein/daemux

    $ python3 setup.py install
    
    

Usage
=======

Documentation
++++++++++++++

Read the documentation https://daemux.readthedocs.io/ to understand how to use daemux.

In the cloned repo
+++++++++++++++++++++

Helper targets
>>>>>>>>>>>>>>>>

To build the documentation, run:

    $ make doc
    
To run the test, run:

    $ make test

To check the code's superficial cleanliness run:

    $ make lint

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

       $ python3 setup.py sdist

       $ twine upload dist/* --skip-existing
        
- If you are the maintainer, check that the docs are updated <http://daemux.readthedocs.io/en/latest/>

- If you are the maintainer or the devops guy, deploy the new code to all relevant machines

