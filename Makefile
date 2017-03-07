all: doc lint test

doc:
	make -C docs html

test:
	coverage run -m doctest daemux/__init__.py

lint:
	flake8 $$(find . -type f -name '*.py' -not -path './docs/*')

fixme:
	find . -type f | xargs grep --color -H -n -i fixme

todo:
	find . -type f | xargs grep --color -H -n -i todo
