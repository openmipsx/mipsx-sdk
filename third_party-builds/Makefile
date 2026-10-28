# Build lwIP, littlefs and BearSSL for MIPS-X with Clang and the SDK
# sysroot, run their self-tests on the simulator and report code sizes.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
#   make MIPSX_LLVM_BIN=~/src/mipsx/llvm-project/build/bin [OPT=-Os|-O2]
#   make check     run the self-tests on the simulator
#   make check-bearssl   run BearSSL's test vectors (slow)
#   make sizes     build at -Os and -O2, with and without assertions, and
#                  print the size table
#
# The sources are upstream checkouts in THIRD_PARTY (see README.md).

SDK := $(abspath ..)
MIPSX_LLVM_BIN ?= $(abspath $(SDK)/../llvm-project/build/bin)
THIRD_PARTY ?= $(abspath $(SDK)/../third_party)
SYSROOT ?= $(SDK)/build/sysroot
OPT ?= -Os
# ASSERT=0 builds without the libraries' assertions (a release build).
ASSERT ?= 1
BUILD := build/$(TAG)$(subst -,,$(OPT))$(if $(filter 0,$(ASSERT)),-noassert)

CC := $(MIPSX_LLVM_BIN)/clang
AR := $(MIPSX_LLVM_BIN)/llvm-ar
SIZE := $(MIPSX_LLVM_BIN)/llvm-size
SIM := $(SDK)/sim/build/mipsx-sim
JOBS ?= 8

CFLAGS := --target=mipsx --sysroot=$(SYSROOT) $(OPT) \
	-ffunction-sections -fdata-sections -Wall -Wno-unused-function \
	$(if $(filter 0,$(ASSERT)),-DNDEBUG -DLWIP_NOASSERT -DLFS_NO_ASSERT) $(EXTRA_CFLAGS)
LDFLAGS = -Wl,--gc-sections -Wl,-Map=$@.map

LWIP := $(THIRD_PARTY)/lwip
LFS := $(THIRD_PARTY)/littlefs
BEARSSL := $(THIRD_PARTY)/bearssl

# lwIP: the core, IPv4, Ethernet and the raw-API apps the firmware needs.
LWIP_SRC := $(addprefix $(LWIP)/src/core/, init.c def.c dns.c inet_chksum.c \
	ip.c mem.c memp.c netif.c pbuf.c raw.c stats.c sys.c altcp.c \
	altcp_alloc.c altcp_tcp.c tcp.c tcp_in.c tcp_out.c timeouts.c udp.c) \
	$(addprefix $(LWIP)/src/core/ipv4/, acd.c autoip.c dhcp.c etharp.c \
	icmp.c igmp.c ip4_frag.c ip4.c ip4_addr.c) \
	$(LWIP)/src/netif/ethernet.c \
	$(LWIP)/src/apps/sntp/sntp.c $(LWIP)/src/apps/tftp/tftp.c \
	$(LWIP)/src/apps/http/fs.c $(LWIP)/src/apps/http/httpd.c
LWIP_INC := -Ilwip -I$(LWIP)/src/include

LFS_SRC := $(LFS)/lfs.c $(LFS)/lfs_util.c
LFS_INC := -I$(LFS) -DLFS_NO_DEBUG -DLFS_NO_WARN

BEARSSL_SRC := $(sort $(wildcard $(BEARSSL)/src/*/*.c))
BEARSSL_INC := -I$(BEARSSL)/inc -I$(BEARSSL)/src

obj = $(patsubst $(THIRD_PARTY)/%.c,$(BUILD)/obj/%.o,$(1))

LIBS := $(BUILD)/liblwip.a $(BUILD)/liblittlefs.a $(BUILD)/libbearssl.a
PROGS := $(BUILD)/lwip_test $(BUILD)/lfs_test $(BUILD)/bearssl_test_crypto \
	$(BUILD)/tls_client_min $(BUILD)/tls_client_full $(BUILD)/baseline

all: $(LIBS) $(PROGS)

$(BUILD)/obj/lwip/%.o: $(LWIP)/%.c lwip/lwipopts.h lwip/arch/cc.h
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $(LWIP_INC) -c $< -o $@
$(BUILD)/obj/littlefs/%.o: $(LFS)/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $(LFS_INC) -c $< -o $@
$(BUILD)/obj/bearssl/%.o: $(BEARSSL)/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $(BEARSSL_INC) -c $< -o $@

$(BUILD)/liblwip.a: $(call obj,$(LWIP_SRC))
$(BUILD)/liblittlefs.a: $(call obj,$(LFS_SRC))
$(BUILD)/libbearssl.a: $(call obj,$(BEARSSL_SRC))
$(LIBS):
	@rm -f $@
	$(AR) rcs $@ $^

$(BUILD)/baseline: baseline.c
	$(CC) $(CFLAGS) $(LDFLAGS) $< -o $@
$(BUILD)/lwip_test: lwip/lwip_test.c $(BUILD)/liblwip.a
	$(CC) $(CFLAGS) $(LWIP_INC) $(LDFLAGS) $^ -o $@
$(BUILD)/lfs_test: littlefs/lfs_test.c $(LFS)/bd/lfs_rambd.c $(BUILD)/liblittlefs.a
	$(CC) $(CFLAGS) $(LFS_INC) $(LDFLAGS) $^ -o $@
$(BUILD)/bearssl_test_crypto: $(BEARSSL)/test/test_crypto.c bearssl/test_main.c $(BUILD)/libbearssl.a
	$(CC) $(CFLAGS) $(BEARSSL_INC) -Wno-unused-variable -Dmain=bearssl_test_main \
		-c $(BEARSSL)/test/test_crypto.c -o $(BUILD)/test_crypto.o
	$(CC) $(CFLAGS) $(LDFLAGS) $(BUILD)/test_crypto.o bearssl/test_main.c $(BUILD)/libbearssl.a -o $@
$(BUILD)/tls_client_min: bearssl/tls_client.c $(BUILD)/libbearssl.a
	$(CC) $(CFLAGS) $(BEARSSL_INC) $(LDFLAGS) $^ -o $@
$(BUILD)/tls_client_full: bearssl/tls_client.c $(BUILD)/libbearssl.a
	$(CC) $(CFLAGS) $(BEARSSL_INC) -DFULL_PROFILE $(LDFLAGS) $^ -o $@

check: $(BUILD)/lwip_test $(BUILD)/lfs_test $(BUILD)/tls_client_min $(BUILD)/tls_client_full
	$(SIM) $(BUILD)/lwip_test
	$(SIM) $(BUILD)/lfs_test
	$(SIM) $(BUILD)/tls_client_min
	$(SIM) $(BUILD)/tls_client_full

# BearSSL's own test vectors, one simulator run per test; about an hour.
# A test stopped by the cycle limit is reported as "timeout", not a failure.
check-bearssl: $(BUILD)/bearssl_test_crypto
	./run_bearssl_tests.sh $(SIM) $< $(BEARSSL)/test/test_crypto.c $(JOBS) | tee $(BUILD)/bearssl_tests.txt
	! grep FAIL $(BUILD)/bearssl_tests.txt

sizes:
	$(MAKE) OPT=-Os all
	$(MAKE) OPT=-O2 all
	$(MAKE) OPT=-Os ASSERT=0 all
	$(MAKE) OPT=-O2 ASSERT=0 all
	python3 sizes.py --readelf $(MIPSX_LLVM_BIN)/llvm-readelf build/Os build/O2 build/Os-noassert build/O2-noassert

clean:
	rm -rf build

.PHONY: all check check-bearssl sizes clean
