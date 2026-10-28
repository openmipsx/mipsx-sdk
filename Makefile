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
#   make sysroot MIPSX_LLVM_BIN=.../llvm-project/build/bin
#                 builds the run-time with llvm-mc and llvm-ar into a sysroot
#                 for clang --target=mipsx (build/sysroot, or SYSROOT=dir):
#                 lib/crt0.o, lib/{sim,device}.ld, lib/lib{sim,device}.a
#                 (_exit), lib/libbuiltins.a (rt/builtins), include/
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

# Run-time sysroot for Clang's MIPS-X driver (llvm-project
# clang/lib/Driver/ToolChains/MIPSX.h describes the layout it expects).
SYSROOT ?= $(CURDIR)/build/sysroot
RTOBJ := build/rt
BUILTINS := $(patsubst rt/builtins/%.S,$(RTOBJ)/builtins/%.o,$(wildcard rt/builtins/*.S))
SYSROOT_FILES := $(SYSROOT)/lib/crt0.o $(SYSROOT)/lib/sim.ld \
	$(SYSROOT)/lib/device.ld $(SYSROOT)/lib/libsim.a \
	$(SYSROOT)/lib/libdevice.a $(SYSROOT)/lib/libbuiltins.a

sysroot: $(SYSROOT_FILES)
	mkdir -p $(SYSROOT)/include

$(RTOBJ)/%.o: rt/%.S
	@test -n "$(MIPSX_LLVM_BIN)" || { echo "set MIPSX_LLVM_BIN to the directory holding llvm-mc and llvm-ar"; exit 1; }
	@mkdir -p $(dir $@)
	$(MIPSX_LLVM_BIN)/llvm-mc -triple=mipsx -filetype=obj $< -o $@

$(SYSROOT)/lib/crt0.o: $(RTOBJ)/crt0.o
	@mkdir -p $(dir $@)
	cp $< $@

$(SYSROOT)/lib/%.ld: rt/%.ld
	@mkdir -p $(dir $@)
	cp $< $@

$(SYSROOT)/lib/libsim.a: $(RTOBJ)/exit-sim.o
	@mkdir -p $(dir $@)
	rm -f $@ && $(MIPSX_LLVM_BIN)/llvm-ar rcs $@ $^

$(SYSROOT)/lib/libdevice.a: $(RTOBJ)/exit-device.o
	@mkdir -p $(dir $@)
	rm -f $@ && $(MIPSX_LLVM_BIN)/llvm-ar rcs $@ $^

$(SYSROOT)/lib/libbuiltins.a: $(BUILTINS)
	@mkdir -p $(dir $@)
	rm -f $@ && $(MIPSX_LLVM_BIN)/llvm-ar rcs $@ $^

clean:
	rm -rf build
	$(MAKE) -C sim clean
	rm -rf rt/tests/__pycache__ tools/tests/__pycache__ tools/__pycache__ sim/tests/__pycache__

.PHONY: all check check-llvm sysroot clean
