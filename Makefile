all: doc lint test

doc:
	make -C docs html

test:
	coverage run --branch --omit '*libtmux*' -m doctest daemux/__init__.py

lint:
	flake8 $$(find . -type f -name '*.py' -not -path './docs/*')

fixme:
	find . -type f | xargs grep --color -H -n -i fixme

todo:
	find . -type f | xargs grep --color -H -n -i todo

live:
	find . -type f -name '*.py' | entr -c sh -c 'coverage erase && make test | head -n 30 && coverage report'
