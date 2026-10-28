# mipsx-sdk: top-level build and tests.
# SPDX-License-Identifier: Apache-2.0
#
#   make          builds the simulator (sim/build/mipsx-sim)
#   make check    simulator tests, crt0 and helper tests (rt/) and packer
#                 tests (tools/)
#
# Needs a C11 compiler and python3 (standard library only).

PYTHON ?= python3

all:
	$(MAKE) -C sim

check: all
	$(MAKE) -C sim check
	MIPSX_SIM=$(CURDIR)/sim/build/mipsx-sim $(PYTHON) -m unittest discover -s rt/tests -t rt/tests
	MIPSX_SIM=$(CURDIR)/sim/build/mipsx-sim $(PYTHON) -m unittest discover -s tools/tests -t tools/tests

clean:
	$(MAKE) -C sim clean
	rm -rf rt/tests/__pycache__ tools/tests/__pycache__ tools/__pycache__ sim/tests/__pycache__

.PHONY: all check clean
