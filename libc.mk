# mipsx-sdk: picolibc build, included by Makefile (docs/picolibc.md).
# SPDX-License-Identifier: Apache-2.0
#
#   make libc MIPSX_LLVM_BIN=...
#                 builds picolibc (PICOLIBC_SRC, default ../picolibc on its
#                 mipsx branch) with Meson in build/picolibc and installs it
#                 into the sysroot: include/, lib/libc.a, lib/libm.a and
#                 lib/libsemihost.a (stdio, read and write on the
#                 simulator's I/O page), whose objects also go into
#                 lib/libsim.a so that printf works with no extra flags
#   make check-libc MIPSX_LLVM_BIN=...
#                 also builds picolibc's tests in build/picolibc-tests and
#                 runs them on the simulator
#   make meson-paths MIPSX_LLVM_BIN=...
#                 writes build/meson-paths.txt, the constants that the
#                 cross file meson/mipsx.txt needs

MESON ?= meson
PICOLIBC_SRC ?= $(CURDIR)/../picolibc
PICOLIBC_BUILD := build/picolibc
PICOLIBC_TESTS := build/picolibc-tests
PICOLIBC_OPTIONS := --buildtype=minsize -Dmultilib=false -Dpicocrt=false \
	-Dthread-local-storage=false -Datomic-ungetc=false -Dspecsdir=none \
	-Dprefix=$(SYSROOT) -Dincludedir=include -Dlibdir=lib
# The simulator has stdin and stdout but no files.
PICOLIBC_TEST_OPTIONS := -Dtests=true -Dtests-enable-posix-io=false

build/meson-paths.txt: FORCE
	@test -n "$(MIPSX_LLVM_BIN)" || { echo "set MIPSX_LLVM_BIN to the directory holding clang and ld.lld"; exit 1; }
	@mkdir -p $(dir $@)
	@printf "[constants]\nllvm_bin = '%s'\nsdk = '%s'\nsysroot = '%s'\n" \
	  "$(abspath $(MIPSX_LLVM_BIN))" "$(CURDIR)" "$(SYSROOT)" > $@.tmp
	@if cmp -s $@.tmp $@; then rm $@.tmp; else mv $@.tmp $@; fi

meson-paths: build/meson-paths.txt

PICOLIBC_SETUP = $(MESON) setup --cross-file build/meson-paths.txt \
	  --cross-file meson/mipsx.txt $(PICOLIBC_OPTIONS)

$(PICOLIBC_BUILD)/build.ninja: build/meson-paths.txt meson/mipsx.txt libc.mk
	$(MAKE) sysroot
	rm -rf $(PICOLIBC_BUILD)
	$(PICOLIBC_SETUP) $(PICOLIBC_BUILD) $(PICOLIBC_SRC)

$(PICOLIBC_TESTS)/build.ninja: build/meson-paths.txt meson/mipsx.txt libc.mk
	$(MAKE) sysroot
	rm -rf $(PICOLIBC_TESTS)
	$(PICOLIBC_SETUP) $(PICOLIBC_TEST_OPTIONS) $(PICOLIBC_TESTS) $(PICOLIBC_SRC)

libc: all $(PICOLIBC_BUILD)/build.ninja
	$(MESON) compile -C $(PICOLIBC_BUILD)
	$(MESON) install -C $(PICOLIBC_BUILD) --quiet
	$(MAKE) sysroot

# Test programs that the compiler cannot build yet are listed and
# skipped (meson/run-built-tests.py).  The simulator is slower than the
# hosts picolibc's timeouts were chosen for.
check-libc: libc $(PICOLIBC_TESTS)/build.ninja
	-ninja -C $(PICOLIBC_TESTS) -k 0
	MIPSX_RUN_MAX_CYCLES=0 MESON=$(MESON) $(PYTHON) meson/run-built-tests.py \
	  $(PICOLIBC_TESTS) --num-processes $$(nproc) --timeout-multiplier 20 \
	  --print-errorlogs

.PHONY: libc check-libc meson-paths FORCE
