PYTHON ?= python3
GUIX_SHELL = guix shell bash python python-libtmux python-pytest python-coverage python-sphinx python-flake8 tmux --

all: doc lint test

doc:
	$(PYTHON) -m sphinx -b html docs docs/_build/html

test:
	tmux kill-session -t yes >/dev/null 2>&1 || true
	$(PYTHON) -m coverage erase
	$(PYTHON) -m coverage run --branch --source=daemux,tests \
		--omit=tests/bug_not_ready.py -m doctest daemux/__init__.py
	$(PYTHON) -m coverage run --branch --source=daemux,tests \
		--omit=tests/bug_not_ready.py -a -m pytest -q
	$(PYTHON) -m coverage report -m
	tmux kill-session -t yes >/dev/null 2>&1 || true

clean:
	rm -rf docs/_build .coverage .pytest_cache
	tmux kill-session -t daemux_test || true  # Created by the tests
	tmux kill-session -t yes || true # Created by the tests

lint:
	$(PYTHON) -m flake8 daemux tests

fixme:
	find . -type f | xargs grep --color -H -n -i fixme

todo:
	find . -type f | xargs grep --color -H -n -i todo

live:
	find . -type f -name '*.py' | entr -c sh -c '$(PYTHON) -m coverage erase && make test | head -n 30'

guix-test:
	$(GUIX_SHELL) $(MAKE) test

guix-doc:
	$(GUIX_SHELL) $(MAKE) doc

guix-lint:
	$(GUIX_SHELL) $(MAKE) lint
