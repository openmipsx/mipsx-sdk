# MIPS-X (ES3890) instruction-set simulator.
# SPDX-License-Identifier: Apache-2.0

CC ?= cc
CFLAGS ?= -O2 -g
WARN = -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Wshadow -Wstrict-prototypes
PYTHON ?= python3
PREFIX ?= /usr/local
BUILD ?= build

SRCS = src/sim.c src/decode.c src/elf.c
HDRS = src/mipsx.h

all: $(BUILD)/mipsx-sim

$(BUILD)/mipsx-sim: $(SRCS) $(HDRS)
	@mkdir -p $(BUILD)
	$(CC) $(WARN) $(CFLAGS) $(LDFLAGS) -o $@ $(SRCS)

check: $(BUILD)/mipsx-sim
	$(PYTHON) tests/run_tests.py --sim $(BUILD)/mipsx-sim --runner ./mipsx-run --work $(BUILD)/tests

install: $(BUILD)/mipsx-sim
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 755 $(BUILD)/mipsx-sim $(DESTDIR)$(PREFIX)/bin/mipsx-sim
	install -m 755 mipsx-run $(DESTDIR)$(PREFIX)/bin/mipsx-run

clean:
	rm -rf $(BUILD)

.PHONY: all check install clean
