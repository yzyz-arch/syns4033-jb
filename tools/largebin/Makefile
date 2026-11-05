CC      ?= gcc
CFLAGS  ?= -g -O0 -fno-tree-vectorize -Wall -Wextra -Wno-unused-parameter -Wno-use-after-free
BINS     = largebin_attack largebin_safe_check largebin_autotune

all: $(BINS)

%: %.c
	$(CC) $(CFLAGS) -o $@ $<

lab: all
	python3 lab.py

clean:
	rm -f $(BINS)

.PHONY: all lab clean
