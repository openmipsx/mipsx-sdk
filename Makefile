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
#                 (_exit and the argv hooks), lib/libbuiltins.a (rt/builtins, rt/atomic.c and
#                 compiler-rt's generic builtins, compiled with the clang in
#                 MIPSX_LLVM_BIN from COMPILER_RT, by default the
#                 compiler-rt/lib/builtins of the llvm-project checkout that
#                 MIPSX_LLVM_BIN was built from), include/
#   make libc, make check-libc
#                 build picolibc into the sysroot and run its tests on the
#                 simulator (libc.mk, docs/picolibc.md)
#
# Needs a C11 compiler and python3 (standard library only); make libc
# also needs meson.

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
BUILTINS += $(RTOBJ)/atomic.o

# compiler-rt's generic builtins (its CMakeLists.txt GENERIC_SOURCES) for
# soft-float, overflow checks, bit counting and so on. Left out: what
# rt/builtins provides, the Apple- and trampoline-specific files, and the
# 128-bit integer ones (MIPS-X has no __int128). long double is double, so
# the GENERIC_TF_SOURCES are not needed either.
COMPILER_RT ?= $(MIPSX_LLVM_BIN)/../../compiler-rt/lib/builtins
CRT_SDK_PROVIDED := ashldi3 ashrdi3 lshrdi3 muldi3 divdi3 moddi3 udivdi3 \
	umoddi3 divsi3 modsi3 udivsi3 umodsi3
CRT_SOURCES := absvdi2 absvsi2 adddf3 addsf3 addvdi3 addvsi3 ashldi3 \
	ashrdi3 bswapdi2 bswapsi2 clzdi2 clzsi2 cmpdi2 comparedf2 \
	comparesf2 ctzdi2 ctzsi2 divdc3 divdf3 divdi3 divmoddi4 divmodsi4 \
	divsc3 divsf3 divsi3 extendsfdf2 extendhfsf2 extendhfdf2 ffsdi2 \
	ffssi2 fixdfdi fixdfsi fixsfdi fixsfsi fixunsdfdi fixunsdfsi \
	fixunssfdi fixunssfsi floatdidf floatdisf floatsidf floatsisf \
	floatundidf floatundisf floatunsidf floatunsisf fp_mode int_util \
	lshrdi3 moddi3 modsi3 muldc3 muldf3 muldi3 mulodi4 mulosi4 mulsc3 \
	mulsf3 mulvdi3 mulvsi3 negdf2 negdi2 negsf2 negvdi2 negvsi2 \
	paritydi2 paritysi2 popcountdi2 popcountsi2 powidf2 powisf2 subdf3 \
	subsf3 subvdi3 subvsi3 truncdfhf2 truncdfsf2 truncsfhf2 ucmpdi2 \
	udivdi3 udivmoddi4 udivmodsi4 udivsi3 umoddi3 umodsi3
CRT_OBJS := $(patsubst %,$(RTOBJ)/compiler-rt/%.o,$(filter-out $(CRT_SDK_PROVIDED),$(CRT_SOURCES)))
BUILTINS += $(CRT_OBJS)
RT_CFLAGS := --target=mipsx -O2 -ffreestanding -fno-builtin -Wall
SYSROOT_FILES := $(SYSROOT)/lib/crt0.o $(SYSROOT)/lib/sim.ld \
	$(SYSROOT)/lib/device.ld $(SYSROOT)/lib/libsim.a \
	$(SYSROOT)/lib/libdevice.a $(SYSROOT)/lib/libbuiltins.a

sysroot: $(SYSROOT_FILES)
	mkdir -p $(SYSROOT)/include

$(RTOBJ)/%.o: rt/%.S
	@test -n "$(MIPSX_LLVM_BIN)" || { echo "set MIPSX_LLVM_BIN to the directory holding llvm-mc and llvm-ar"; exit 1; }
	@mkdir -p $(dir $@)
	$(MIPSX_LLVM_BIN)/llvm-mc -triple=mipsx -filetype=obj $< -o $@

$(RTOBJ)/atomic.o: rt/atomic.c
	@test -n "$(MIPSX_LLVM_BIN)" || { echo "set MIPSX_LLVM_BIN to the directory holding clang"; exit 1; }
	@mkdir -p $(dir $@)
	$(MIPSX_LLVM_BIN)/clang $(RT_CFLAGS) -c $< -o $@

$(RTOBJ)/compiler-rt/%.o: $(COMPILER_RT)/%.c
	@test -n "$(MIPSX_LLVM_BIN)" || { echo "set MIPSX_LLVM_BIN to the directory holding clang"; exit 1; }
	@mkdir -p $(dir $@)
	$(MIPSX_LLVM_BIN)/clang $(RT_CFLAGS) -c $< -o $@

$(SYSROOT)/lib/crt0.o: $(RTOBJ)/crt0.o
	@mkdir -p $(dir $@)
	cp $< $@

$(SYSROOT)/lib/%.ld: rt/%.ld
	@mkdir -p $(dir $@)
	cp $< $@

# Once picolibc is installed (make libc), libsim.a also carries its
# simulator stdio, libsemihost.a.
$(SYSROOT)/lib/libsim.a: $(RTOBJ)/exit-sim.o $(RTOBJ)/args-sim.o $(wildcard $(SYSROOT)/lib/libsemihost.a)
	@mkdir -p $(dir $@)
	rm -f $@ && $(MIPSX_LLVM_BIN)/llvm-ar rcs $@ $(filter %.o,$^)
	if [ -f $(SYSROOT)/lib/libsemihost.a ]; then \
	  rm -rf $(RTOBJ)/semihost && mkdir -p $(RTOBJ)/semihost && \
	  (cd $(RTOBJ)/semihost && \
	   $(MIPSX_LLVM_BIN)/llvm-ar x $(SYSROOT)/lib/libsemihost.a) && \
	  $(MIPSX_LLVM_BIN)/llvm-ar rcs $@ $(RTOBJ)/semihost/*.o; \
	fi

$(SYSROOT)/lib/libdevice.a: $(RTOBJ)/exit-device.o $(RTOBJ)/args-device.o
	@mkdir -p $(dir $@)
	rm -f $@ && $(MIPSX_LLVM_BIN)/llvm-ar rcs $@ $^

$(SYSROOT)/lib/libbuiltins.a: $(BUILTINS)
	@mkdir -p $(dir $@)
	rm -f $@ && $(MIPSX_LLVM_BIN)/llvm-ar rcs $@ $^

include libc.mk

clean:
	rm -rf build
	$(MAKE) -C sim clean
	rm -rf rt/tests/__pycache__ tools/tests/__pycache__ tools/__pycache__ sim/tests/__pycache__

.PHONY: all check check-llvm sysroot clean
