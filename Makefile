# mipsx-sdk: top-level build and tests.
# SPDX-License-Identifier: Apache-2.0
#
#   make          builds the simulator (sim/build/mipsx-sim)
#   make check    simulator tests, crt0 and helper tests (rt/) and packer
#                 tests (tools/)
#   make check-llvm MIPSX_LLVM_BIN=.../llvm-project/build/bin
#                 also builds crt0 with llvm-mc and ld.lld, links it with
#                 rt/sim.ld and rt/device.ld, runs and packs it
#                 (rt/tests/test_llvm.py; skipped by 'make check' unless
#                 MIPSX_LLVM_BIN is set)
#
# Needs a C11 compiler and python3 (standard library only).

PYTHON ?= python3
MIPSX_LLVM_BIN ?=
export MIPSX_LLVM_BIN

all:
	$(MAKE) -C sim

check: all
	$(MAKE) -C sim check
	MIPSX_SIM=$(CURDIR)/sim/build/mipsx-sim $(PYTHON) -m unittest discover -s rt/tests -t rt/tests
	MIPSX_SIM=$(CURDIR)/sim/build/mipsx-sim $(PYTHON) -m unittest discover -s tools/tests -t tools/tests

check-llvm: all
	@test -n "$(MIPSX_LLVM_BIN)" || { echo "set MIPSX_LLVM_BIN to the directory holding llvm-mc and ld.lld"; exit 1; }
	MIPSX_SIM=$(CURDIR)/sim/build/mipsx-sim $(PYTHON) -m unittest discover -v -s rt/tests -t rt/tests -p test_llvm.py

clean:
	$(MAKE) -C sim clean
	rm -rf rt/tests/__pycache__ tools/tests/__pycache__ tools/__pycache__ sim/tests/__pycache__

.PHONY: all check check-llvm clean
