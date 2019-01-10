# Makefile to help automate tasks
PY := bin/python
PIP := bin/pip
PYTEST := bin/py.test
THEBLUES := lib/python*/site-packages/theblues.egg-link
FLAKE8 := bin/flake8
SPHINX := bin/sphinx-apidoc
TOX := bin/tox
VPART ?= patch

SYSDEPS := libyaml-cpp-dev python-dev python3-dev python-yaml python3-yaml libsodium-dev virtualenv

help:
	@echo "bumpversion - bump version."
	@echo "  By default bumps patch level. 'VPART=[major|minor|patch] make bumpversion' to specify."
	@echo "dev - install theblues in develop mode"
	@echo "lint - check style with flake8"
	@echo "test - run tests quickly with the default Python"
	@echo "check - clean env, run tests against 2.7 and 3.4, check lint,"
	@echo "test-all - run tests against 2.7 and 3.4, check lint, and test docs"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "clean - remove build and python artifacts"


#######
# TOOLS
#######
$(PY):
	virtualenv .

$(PYTEST): $(PY)
	$(MAKE) testdeps

$(TOX): $(PY)
	$(MAKE) testdeps

$(FLAKE8): $(PY)
	$(MAKE) testdeps

$(SPHINX): $(PYTEST)
	$(MAKE) devdeps

#########
# INSTALL
#########
.PHONY: all
all: venv deps dev


venv: $(PY)

$(THEBLUES):
	$(PY) setup.py develop

.PHONY: dev
dev: venv $(THEBLUES)


######
# DEPS
######
.PHONY: sysdeps
sysdeps:
	sudo apt-get install --yes $(SYSDEPS)

.PHONY: deps
deps: venv lib/python2.7/site-packages/macaroons.so
	$(PIP) install -r requirements.txt

lib/python2.7/site-packages/macaroons.so:
	# Link system installed macaroon lib to virtual env
	ln -s /usr/lib/python2.7/dist-packages/macaroons.so lib/python2.7/site-packages

.PHONY: testdeps
testdeps: deps venv
	$(PIP) install -r test-requirements.txt

.PHONY: dev-deps
devdeps: deps venv
	$(PIP) install -r dev-requirements.txt


#######
# Tests
#######
.PHONY: test
test: venv dev $(PYTEST)
	$(PYTEST) -s theblues/tests

.PHONY: coverage
coverage: deps venv dev $(PYTEST)
	$(PYTEST) --cov=theblues -s theblues/tests

.PHONY: test-all
test-all: $(TOX)
	$(TOX)

.PHONY: check
check: clean test-all

lint: $(FLAKE8)
	$(FLAKE8) theblues


######
# DOCS
######
.PHONY: docs
docs: $(SPHINX)
	rm -f docs/theblues.rst
	rm -f docs/modules.rst
	bin/sphinx-apidoc -o docs/ theblues
	$(MAKE) -C docs clean
	$(MAKE) -C docs html


######
# DIST
######
.PHONY: bumpversion
bumpversion: devdeps
	bin/bumpversion $(VPART)

.PHONY: dist
dist:
	python setup.py sdist

.PHONY: upload
upload: dist
	python setup.py sdist upload


#######
# CLEAN
#######
.PHONY: clean-docs
clean-docs:
	- rm -rf docs/_build/*

.PHONY: clean-venv
clean-venv:
	- rm -rf bin include lib local man share build .tox

.PHONY: clean-pyc
clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

clean-dist:
	- rm -rf dist

.PHONY: clean
clean: clean-venv clean-pyc clean-docs
	rm -fr *.egg-info
