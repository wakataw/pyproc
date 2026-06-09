.PHONY: test test-verbose test-lpse test-downloader install clean build

PYTHON ?= python3
VENV = .venv
VENV_PYTHON = $(VENV)/bin/python
VENV_PIP = $(VENV)/bin/pip

# Create venv and install dependencies
install: $(VENV)/bin/activate

$(VENV)/bin/activate: pyproject.toml
	$(PYTHON) -m venv --without-pip $(VENV)
	curl -sS https://bootstrap.pypa.io/get-pip.py | $(VENV_PYTHON)
	$(VENV_PIP) install pytest
	$(VENV_PIP) install -e .
	touch $(VENV)/bin/activate

# Run tests
test: install
	$(VENV_PYTHON) -m pytest

# Run tests with verbose output
test-verbose: install
	$(VENV_PYTHON) -m pytest -v

# Run tests for a specific file
test-lpse: install
	$(VENV_PYTHON) -m pytest tests/test_lpse.py

test-downloader: install
	$(VENV_PYTHON) -m pytest tests/test_downloader.py

# Clean build artifacts and test outputs (keeps .venv)
clean:
	rm -rf ./dists ./pyproc.egg-info ./tests/*.csv ./tests/*.idx ./*csv ./*idx ./build ./*.egg-info ./.pytest_cache __pycache__ ./**/__pycache__

# Build the package
build: install
	$(VENV_PYTHON) -m build
