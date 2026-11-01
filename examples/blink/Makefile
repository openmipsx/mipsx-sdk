# examples/blink: the first SPA3000 image.  See README.md.
# SPDX-License-Identifier: Apache-2.0
#
#   make MIPSX_LLVM_BIN=.../llvm-project/build/bin [SYSROOT=.../build/sysroot]
#         builds blink.bin (watchdog left alone) and blink-wd.bin (watchdog
#         enabled) and checks both with tools/mipsx_verify.py
#   make sim        builds blink-sim.elf, the simulator build with
#                   sim/model.c in place of the hardware
#   make check      also runs tests/test_blink.py on the simulator
#   make O=dir      puts every output in dir
#   make CFLAGS_EXTRA=-DBLINK_KICK_STOP_S=60
#                   build options: -DARM_SECONDS=N (default 15),
#                   -DBLINK_KICK_STOP_S=N (default 0); see README.md
#
# SYSROOT defaults to the SDK's build/sysroot (make sysroot at the top
# level); in a worktree point it at a built one.

MIPSX_LLVM_BIN ?=
SDK      := $(abspath ../..)
SYSROOT  ?= $(SDK)/build/sysroot
MIPSX_SIM ?= $(SDK)/sim/build/mipsx-sim
PYTHON   ?= python3
O        ?= .
VERSION  ?= 9.0.1

ifeq ($(MIPSX_LLVM_BIN),)
CLANG := clang
else
CLANG := $(MIPSX_LLVM_BIN)/clang
endif

CFLAGS := --target=mipsx --sysroot=$(SYSROOT) -Os -std=c11 -ffreestanding \
          -fno-builtin -Wall -Wextra -g $(CFLAGS_EXTRA)
SRCS   := main.c board.c bootrec.c flash.c util.c
DEVICE_SRCS := $(SRCS) vectors.S
SIM_SRCS := $(SRCS) sim/model.c
HDRS   := board.h board_io.h bootrec.h flash.h hal.h util.h

all: $(O)/blink.bin $(O)/blink-wd.bin

$(O)/blink.elf: $(DEVICE_SRCS) $(HDRS) | $(O)
	$(CLANG) $(CFLAGS) -mboard=device -DBLINK_WATCHDOG=0 $(DEVICE_SRCS) -o $@

$(O)/blink-wd.elf: $(DEVICE_SRCS) $(HDRS) | $(O)
	$(CLANG) $(CFLAGS) -mboard=device -DBLINK_WATCHDOG=1 $(DEVICE_SRCS) -o $@

$(O)/%.bin: $(O)/%.elf
	$(PYTHON) $(SDK)/tools/mipsx_pack.py $< -o $@ --version $(VERSION)
	$(PYTHON) $(SDK)/tools/mipsx_verify.py $@

sim: $(O)/blink-sim.elf

$(O)/blink-sim.elf: $(SIM_SRCS) $(HDRS) | $(O)
	$(CLANG) $(CFLAGS) -DBLINK_SIM -DARM_SECONDS=3 $(SIM_SRCS) -o $@

$(O):
	mkdir -p $(O)

check: all sim
	MIPSX_SIM=$(MIPSX_SIM) BLINK_BUILD=$(abspath $(O)) \
	$(PYTHON) -m unittest discover -v -s tests -t tests

clean:
	rm -f $(O)/blink.elf $(O)/blink-wd.elf $(O)/blink.bin $(O)/blink-wd.bin \
	      $(O)/blink-sim.elf

.PHONY: all sim check clean
