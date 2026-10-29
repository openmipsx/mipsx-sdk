# MIPS-X ABI for the ES3890

Status: version 1, 2026-10-28 (§8.6 and the DWARF rules of §2.4 and §4
added in S17). Written in work package S1 of
the LLVM backend plan. Clean-side document.

This document is the contract between the LLVM backend (assembler,
object writer, lld, code generator, Clang), the simulator, the start-up
code and hand-written assembly. Every later work package implements from
it. Where something here disagrees with the code, one of them is a bug;
fix the code or change this document in the same commit.

Sources: the [processor spec](https://github.com/openmipsx/devices/blob/main/common/processor-es3890.md)
("spec §n") and Paul Chow's *MIPS-X Instruction Set and Programmer's
Manual* ("manual §n"). The stock firmware's convention (spec §7) informed
some choices, but this ABI is ours and does not need to interoperate with
vendor code.

Bits are numbered from the least significant bit (bit 0), as in the spec.
"Word" means 32 bits. Hexadecimal addresses are byte addresses unless
marked otherwise.

Contents:

1. Basic facts
2. Registers
3. Data types and layout
4. Addresses: bytes and words
5. Calls, jumps and branches
6. Constants and global addresses
7. Calling convention
8. Stack frame
9. Pipeline rules for code generators
10. Assembler syntax
11. ELF
12. Relocations
13. Linking, start-up and the run-time environment
14. Decisions and rationale
15. Questions each work package may ask

## 1. Basic facts

- 32-bit, big-endian, 32 general registers, r0 reads as zero.
- Code is word-addressed (PC, branch displacements, `jspci` targets,
  return addresses); data is byte-addressed (spec §1).
- Two delay slots after every branch and jump; branches can squash them
  (spec §4). `jspci`, `jpc` and `jpcrs` never squash.
- `trap` has no delay slots: the instruction after it does not execute
  before the handler, which restarts it on return (manual Appendix VI,
  Figure VI-2). The simulator gives `trap` two bubbles.
- No interlocks: one load delay slot, and other rules in §9.
- Immediates are 17-bit signed (−65536 to 65535). Branch displacements
  are 16-bit signed words.
- No multiply, divide, set-on-compare, load-upper-immediate or variable
  shift.
- No floating-point hardware: the ABI is soft-float only.
- No position-independent code, shared libraries, dynamic linking or
  thread-local storage. Programs are statically linked.

## 2. Registers

### 2.1 General registers

| Register | Alias | Role | Preserved across calls |
|---|---|---|---|
| r0 | `zero` | Always zero | (constant) |
| r1 | `at` | Assembler and code-generator temporary (§2.2) | No |
| r2 | | Return value word 0; temporary | No |
| r3 | | Return value word 1; temporary | No |
| r4–r11 | | Arguments 1–8; temporaries | No |
| r12–r15 | | Temporaries | No |
| r16–r22 | | Saved registers | Yes |
| r23 | `cb0` | Code base 0, a word address (§5.2). Reserved | (constant) |
| r24 | `cb1` | Code base 1, a word address (§5.2). Reserved | (constant) |
| r25–r27 | | Saved registers | Yes |
| r28 | `gp` | Global pointer for small data (§6.3). Reserved | (constant) |
| r29 | `sp` | Stack pointer | Yes |
| r30 | `fp` | Frame pointer when a function needs one, else a saved register | Yes |
| r31 | `ra` | Return address, a word address (§5.1) | No |

Summary for the register allocator:

- Never allocated: r0, r1, r23, r24, r28, r29. r30 is not allocated in
  functions that use a frame pointer.
- Caller-saved (clobbered by a call): r1–r15, r31, MD.
- Callee-saved: r16–r22, r25–r27, r29, r30. A function that changes one
  of these restores it before returning.
- r23, r24 and r28 are set once by the start-up code (§13.3) and never
  written afterwards, so no function saves them. Interrupt handlers do
  not need to save them either.
- Suggested allocation order: r2–r15 first (no save cost), then r16–r22,
  r25–r27, r30.

There are 14 caller-saved and 11 callee-saved allocatable registers.

### 2.2 The `at` register

r1 is never allocated, so code that has to be produced after register
allocation always has a scratch register. Users:

- Long-call sequences (§5.4).
- Stack offsets that do not fit in 17 bits (§8.4).
- Any other late expansion that needs one temporary.

No assembler pseudo-instruction uses r1 implicitly (§10.5), and the
linker never inserts code. Hand-written assembly may use r1 freely, but a
call clobbers it.

### 2.3 Special registers

| Name in assembly | Spec number | Notes |
|---|---|---|
| `psw` | 1 | Processor status word |
| `md` | 2 | Multiply/divide register. Caller-saved: any call may change it, including calls to the multiply and divide helpers |
| `pcm4` | 4 | PC chain, read form (PC-4); used with `movfrs` |
| `pcm1` | 4 | PC chain, write form (PC-1); used with `movtos` |

User code never writes `psw`. Only exception and interrupt handlers use
the PC chain.

The bit layout of the PSW (manual §2.4, Figure 2-3) is **not confirmed
for the ES3890**: the processor spec does not describe it. The simulator
uses the manual's layout; code that reads or writes PSW bits (handlers,
crt0's overflow mask, §13.3) must be checked on hardware before relying
on it.

### 2.4 DWARF register numbers

r0–r31 are DWARF registers 0–31; `psw` is 32 and `md` is 33. `pcm4` and
`pcm1` have no DWARF number. The return address column of the call frame
information is 31.

r31 and its stack slot hold a word address, but every DWARF address is a
byte address (§4), so the rule for column 31 always yields the byte
return address: it is a `DW_CFA_val_expression` that multiplies by 4
(§8.6, D15). An unwinder that follows the standard rules gets byte
addresses with no MIPS-X knowledge; the recovered value of "r31" in a
caller's frame is that byte address, not the word the hardware held.

## 3. Data types and layout

| C type | Size | Alignment | Notes |
|---|---|---|---|
| `_Bool` | 1 | 1 | 0 or 1 |
| `char` | 1 | 1 | **Signed** |
| `short` | 2 | 2 | |
| `int`, `long` | 4 | 4 | |
| `long long` | 8 | 8 | |
| pointers, `size_t`, `ptrdiff_t`, `intptr_t` | 4 | 4 | `size_t` is `unsigned int`, `ptrdiff_t` is `int` |
| `wchar_t` | 4 | 4 | Signed (`int`) |
| `float` | 4 | 4 | IEEE 754 single, in software |
| `double`, `long double` | 8 | 8 | IEEE 754 double, in software. `long double` is the same as `double` |
| `enum` | 4 | 4 | Unless the enum is packed |

- Multi-byte values are big-endian in memory.
- Aggregates are aligned to their most-aligned member and padded to a
  multiple of that alignment. `max_align_t` has alignment 8.
- Bit-fields follow the usual big-endian rules (Clang's default for a
  big-endian target): allocated from the most significant bit of their
  storage unit.
- LLVM data layout string: `E-m:e-p:32:32-i64:64-n32-S64`.

Word loads and stores need 4-byte-aligned addresses and halfword
accesses need 2-byte alignment. The hardware drops the low address bits
(manual §2.1), so a misaligned access silently touches the wrong bytes;
the simulator reports it as an error.

## 4. Addresses: bytes and words

The one rule: **every address that is a value is a byte address.**

- ELF symbol values, section addresses, `e_entry` and program header
  addresses are byte addresses, for code as well as data. This differs
  from the manual's assembler, where labels in `.text` had word values
  (manual Appendix VII.2).
- C pointers, including function pointers and label addresses
  (`&&label`), are byte addresses. Function pointers compare, cast and
  round-trip through integers like data pointers. A null function
  pointer is 0.
- Code is always 4-byte aligned, so byte address = word address × 4.

Word addresses appear only inside instructions and in a few places the
hardware or the ABI requires:

| Where | Unit |
|---|---|
| Branch displacement field | Words, relative (§5.3) |
| `jspci` register value + immediate | Words, absolute |
| r23 (`cb0`), r24 (`cb1`) | Words |
| r31 after a call, and a saved return address on the stack | Words |
| Jump-table entries (§5.6) | Words |
| Trap vectors | `trap n` jumps to word n × 8 (spec §6) |

Conversions: byte to word is a logical shift right by 2
(`lsr rs,rd,#2`), word to byte a shift left by 2. The relocation
operators `%w()` and `%call()` do the conversion at link time (§12).

`__builtin_return_address(0)` returns a byte address: the backend shifts
r31 left by 2.

Debug information uses byte addresses too: `DW_AT_low_pc`, `DW_AT_high_pc`
(as a length in bytes), range and location lists, `.debug_addr`, the line
table (`DW_LNE_set_address`, and address advances with
`minimum_instruction_length` 4) and the initial locations of `.debug_frame`
and `.eh_frame` FDEs (code alignment factor 4). They are ordinary
R_MIPSX_32 relocations (R_MIPSX_32_PCREL in `.eh_frame`) against byte
symbol values, so `llvm-dwarfdump`, `llvm-objdump --line-numbers` and
`llvm-symbolizer` work with byte addresses, as on any other target. A
debugger stub that receives a word PC from the hardware multiplies it by 4
before looking anything up.

## 5. Calls, jumps and branches

### 5.1 The call instruction

`jspci rB,#imm,rD` jumps to word address rB + imm and writes the word
address of the instruction after its two delay slots (the `jspci`'s own
word address + 3) to rD. The two delay slots always execute.

- Call: `jspci rB,#imm,r31`.
- Return: `jspci r31,#0,r0` (pseudo-instruction `ret`).
- Jump or tail call: `jspci rB,#imm,r0`.

### 5.2 Direct calls: linker-selected code base

A direct call, direct tail call or far jump is one instruction:

```
    jspci r0,#%call(func),r31     ; written "call func"
    <delay slot 1>
    <delay slot 2>
```

The `%call` relocation (R_MIPSX_CALL17, §12) lets the linker choose the
base register: it tries, in this order,

| Base register | Base value (word address) | Reaches (byte addresses) |
|---|---|---|
| r0 | 0 | 0x00000000–0x0003FFFC |
| r23 (`cb0`) | `__mipsx_cb0` / 4 | `__mipsx_cb0` − 0x40000 to `__mipsx_cb0` + 0x3FFFC |
| r24 (`cb1`) | `__mipsx_cb1` / 4 | `__mipsx_cb1` − 0x40000 to `__mipsx_cb1` + 0x3FFFC |

and uses the first one for which (target word − base) fits in a signed 17-bit field.
It writes that register's number into the Src1 field (bits 26–22) and the
offset into the immediate field. The Src1 written by the assembler (r0
for `call`) is only a placeholder. If no base reaches the target, the link
fails with an error naming the call site and target.

`__mipsx_cb0` and `__mipsx_cb1` are byte addresses, multiples of 4,
defined by the linker script (§13.1). The default places them so that
cb0 covers the first 512 KB of `.text` and cb1 the next 512 KB, so 1 MB
of code is always reachable, plus whatever lies below 256 KB through r0.
The start-up code loads r23 = `__mipsx_cb0` >> 2 and r24 =
`__mipsx_cb1` >> 2 before any call (§13.3).

The assembler never resolves `%call` itself, even for a local target,
because the base values are known only at link time.

### 5.3 Branches

Conditional branches compare two registers and reach ±32K words
(±128 KB): target word = branch word + 2 + disp (spec §4). The six
conditions are `eq`, `ne`, `lt`, `ge` (signed), `lo`, `hs` (unsigned);
`gt`, `le`, `hi`, `ls` swap the operands (§10.5). An unconditional branch
is `beq r0,r0,label` (pseudo `b`).

Branches are position-independent and are always preferred to `jspci`
inside a function.

### 5.4 Long calls (option)

With `-mlong-calls` (an LLVM subtarget feature `long-calls`, and a Clang
option of the same name in S13), direct calls use:

```
    la   func,r1           ; 3 instructions (§6.2), byte address
    lsr  r1,r1,#2          ; to word address
    jspci r1,#0,r31
    <delay slot 1>
    <delay slot 2>
```

This reaches any address. It is not the default; use it only if a
program's code outgrows §5.2's reach.

### 5.5 Far branches

A conditional branch whose target is more than ±32K words away (only
possible in a function larger than 128 KB) is relaxed by the code
generator, using LLVM's branch relaxation pass, into an inverted branch
around a jump:

```
    bINV  a,b,1f           ; inverted condition
    nop
    nop
    jspci r0,#%call(target),r0
    nop
    nop
1:
```

The jump uses the same `%call` relocation as a direct call, so it needs
no scratch register. The assembler does not relax: a branch to a local
label that is out of range is an error, and the linker reports
out-of-range R_MIPSX_PC16 relocations.

### 5.6 Indirect calls, computed jumps and jump tables

An indirect call through a function pointer (a byte address in rF):

```
    lsr   rF,rT,#2         ; rT is any free register; may be rF itself
    jspci rT,#0,r31
    <delay slot 1>
    <delay slot 2>
```

Jump tables hold **word** addresses (`.word %w(label)`, relocation
R_MIPSX_32W), so dispatch needs no shift: load the entry, then
`jspci rE,#0,r0`, with at least one instruction between the load and the
`jspci` (§9). Tables live in `.rodata`. Computed `goto` uses byte
addresses, like any pointer, and so shifts like an indirect call.

## 6. Constants and global addresses

### 6.1 Constants

A constant that fits in 17 bits signed is one `addi r0,#imm,rd`.
Otherwise, for the `li` pseudo-instruction and as the code generator's
default (S9 may do better per case):

1. If the value is v = s << t with s fitting in 17 bits signed (t the
   number of trailing zero bits): `addi r0,#s,rd` then `lsl rd,rd,#t`.
2. Otherwise the hi/lo form, which handles every 32-bit value:

```
    addi r0,#hi,rd         ; hi = v >> 15 (arithmetic), always fits 17 bits
    lsl  rd,rd,#15         ; sh r0,rd,rd,#17
    addi rd,#lo,rd         ; lo = v & 0x7FFF, 0 to 32767
```

There is no literal pool in version 1 (§14, D5).

### 6.2 Addresses of symbols

The address of a symbol (code or data, plus a constant offset) uses the
same hi/lo form with relocations, always three instructions:

```
    addi r0,#%hi(sym),rd   ; R_MIPSX_HI17
    lsl  rd,rd,#15
    addi rd,#%lo(sym),rd   ; R_MIPSX_LO15
```

This is the `la sym,rd` pseudo-instruction. Since `%lo` is never
negative, a load or store can use it directly as its offset, with no
carry adjustment:

```
    addi r0,#%hi(var),r2
    lsl  r2,r2,#15
    ld   %lo(var)[r2],r3
```

Addresses in the top or bottom 64 KB of the address space can be used
in one instruction through r0 (`ld sym[r0],rd`, relocation
R_MIPSX_ABS17). The simulator's I/O page (§13.5) is placed there for
this reason.

### 6.3 Small data

r28 (`gp`) holds `_gp`, a byte address set by the linker script and
loaded by the start-up code. Data in `.sdata` and `.sbss` within ±64 KB
of `_gp` can be reached in one instruction:

```
    ld    %gprel(var)[gp],r3      ; R_MIPSX_GPREL17
    addi  gp,#%gprel(var),r3      ; address of var
```

The register is reserved and set up in version 1, so all objects are
compatible, but the code generator does not have to use it. Since S16
it does, like GCC for MIPS with `-G 8`: variables of at most 8 bytes
(`-mllvm -mipsx-ssection-threshold=N`, 0 to turn it off), small
constants included, go in `.sdata`/`.sbss` (`.sdata.name`/`.sbss.name`
with `-fdata-sections`), and are reached through gp when the address is
inside the variable. External variables of a small type are assumed to
be small data too (`-mllvm -mipsx-extern-sdata=false` to stop that);
undefined weak, common and unsized ones are not, nor are variables with
an explicit section other than `.sdata*`/`.sbss*`. All objects of a
program should be built with the same threshold. A disagreement, or more
than 128 KB of small data, cannot give a wrong address: the linker
reports an R_MIPSX_GPREL17 range error.

## 7. Calling convention

### 7.1 Argument words

Each argument is turned into a sequence of 32-bit words:

| Argument | Words |
|---|---|
| Integer or pointer, 32 bits or narrower | 1. Values narrower than 32 bits are sign- or zero-extended to 32 bits **by the caller**, according to their type (`_Bool` is zero-extended) |
| `float` | 1 (the IEEE bits) |
| `long long`, `double` | 2, most significant word first |
| Aggregate (struct, union, array in a struct) up to 16 bytes | ⌈size / 4⌉, as if loaded word by word from memory: the first word holds bytes 0–3. A last partial word is left-justified (bytes in the high-order end); its padding bits are undefined |
| Aggregate larger than 16 bytes | 1: a pointer to a copy that the caller made. The callee may modify the copy. The copy is in the caller's frame, 8-byte aligned |
| Empty aggregate (size 0) | None |

Words are assigned in order to r4, r5, …, r11, then to stack slots at
sp + 0, sp + 4, … at the call (§8.1). Each stack slot is 4 bytes, and
8-byte values have no extra alignment on the stack. Because every word
takes the next free location, a two-word value can be split between r11
and sp + 0, and registers are never back-filled.

In LLVM terms: `i64` and `f64` are split into two `i32` parts by the type
legaliser; for a big-endian target the high part comes first, which gives
the order above. Clang (S13) passes small aggregates as `[N x i32]`
(direct) and large ones indirectly (not `byval`), and marks narrow
integer arguments `signext` or `zeroext`.

S13 settled the cases the table leaves open: complex numbers and
`_BitInt(N)` with N > 64 are aggregates of their size; a one-word
aggregate is `i32` rather than `[1 x i32]`; a C++ class that cannot be
passed in registers (non-trivial copy or destructor) is passed by
reference like a large aggregate; `_BitInt(N)` up to 32 bits is extended
like an integer of its signedness.

### 7.2 Variadic functions

Arguments that match the `...` of a variadic function are **always
passed on the stack**, never in registers, even if argument registers
are free. Named arguments are passed as usual. The variadic words follow
the last stack word of the named arguments (or start at sp + 0).

- `va_list` is `char *`, pointing at the next variadic word.
- `va_start` sets it to the address of the first variadic word, which
  is CFA + 4 × (number of named-argument words beyond r11). The callee
  does not need a register save area.
- `va_arg(ap, T)` reads ⌈sizeof(T) / 4⌉ words at `ap` and advances `ap`
  by that many words. No 8-byte alignment. An aggregate larger than 16
  bytes is read as a pointer. Default promotions apply (`float` becomes
  `double`, narrow integers become `int`).

Calling a variadic function without a prototype in scope is undefined, as
in C99; code that does it will not work.

### 7.3 Return values

| Return type | Where |
|---|---|
| `void` | Nothing |
| Integer or pointer, 32 bits or narrower | r2. Narrower values are sign- or zero-extended to 32 bits **by the callee** |
| `float` | r2 |
| `long long`, `double` | r2 = most significant word, r3 = least significant |
| Aggregate up to 8 bytes | r2, r3, as if loaded word by word from memory (as for arguments) |
| Aggregate larger than 8 bytes | In memory: the caller passes the address of a result buffer as a hidden first argument in r4, and the real arguments start at r5. The callee does not have to return the address; r2 is undefined after the call |

### 7.4 What a call preserves

The callee preserves r16–r22, r25–r27, r29 (sp, restored to its value at
entry) and r30; it never writes r23, r24 or r28. Everything else,
including r1, r31 and MD, may change. PSW is not changed by ordinary
code.

Helper routines for multiply, divide and variable shift (S12) use this
convention like any other function. S12 may document a cheaper private
convention for some of them (for example one that preserves more
registers); if it does, it goes in this section.

S12 (SDK half) did: `rt/builtins/README.md` lists the registers each
helper actually changes (all within the standard set) and two extra
results, the remainder of `__udivsi3` in r3 and of `__udivdi3` in
r4:r5. Division by zero returns quotient 0 and remainder n.

## 8. Stack frame

### 8.1 Layout

The stack grows downwards. sp is 8-byte aligned at every call and at
every function entry. There is no red zone: nothing below sp is
preserved, because interrupt handlers may use the stack.

```
          higher addresses
        +----------------------------+
        | caller's frame             |
        | incoming stack arguments   |  CFA + 0, + 4, ...   (§7.1)
CFA ->  +----------------------------+  = sp at entry, 8-aligned
        | saved r31 (if fp used)     |  CFA - 4
        | saved r30 (if fp used)     |  CFA - 8
        | other saved registers,     |
        | locals and spill slots     |  order chosen by the backend
        +----------------------------+
        | dynamic allocas            |  (only with a frame pointer)
        +----------------------------+
        | outgoing argument area     |  sp + 0, + 4, ...
sp  ->  +----------------------------+  8-aligned
          lower addresses
```

- The CFA (canonical frame address) is the value of sp at entry to the
  function.
- The outgoing argument area is big enough for the largest call the
  function makes, and is reserved in the prologue: sp does not move
  around calls.
- There is no home area for register arguments.
- A leaf function that needs no stack does not adjust sp.

### 8.2 Frame pointer

A function uses a frame pointer when it has variable-sized objects
(`alloca`, VLAs), when the stack is realigned beyond 8 bytes, or when
asked (`-fno-omit-frame-pointer`). Then:

- r30 = CFA for the body of the function.
- The return address r31 (a word address) is saved at CFA − 4 and the
  caller's r30 at CFA − 8.

So from any frame with a frame pointer, the previous frame pointer is at
[fp − 8] and the return word address at [fp − 4]. This lets a debugger
stub walk the stack without unwind tables, if code is compiled with
`-fno-omit-frame-pointer`.

Without a frame pointer, where r31 and other registers are saved is the
backend's choice, described by CFI (§8.6).

### 8.3 Dynamic allocation

`alloca(n)` rounds n up to a multiple of 8, subtracts it from sp, and
returns sp + (size of the outgoing argument area), so the outgoing area
stays at sp + 0.

### 8.4 Large frames

`addi` and memory offsets reach ±64 KB. For a larger frame, the prologue
and epilogue build the adjustment in r1 (§6.1) and use `add`/`sub` with
sp; spill-slot accesses beyond 17 bits compute the address in r1. The
register scavenger is not needed because r1 is reserved.

### 8.5 Prologue and epilogue example

```
func:
    addi  sp,#-16,sp
    st    12[sp],r31
    st    8[sp],r16
    ...
    ld    8[sp],r16
    ld    12[sp],r31
    nop                    ; load delay (P1): ret reads r31
    jspci r31,#0,r0        ; ret
    addi  sp,#16,sp        ; delay slot 1
    nop                    ; delay slot 2 (must not be a load, §9.2)
```

### 8.6 Call frame information

The compiler emits CFI when it emits debug information or unwind tables
(`-g`, `-funwind-tables`); otherwise there is none (bare-metal default, no
C++ exceptions). Without `-funwind-tables` it goes in `.debug_frame`.

- **Initial state (CIE)**: CFA = r29 + 0; column 31 (return address) =
  `DW_CFA_val_expression 31: DW_OP_drop; DW_OP_breg31 0; DW_OP_lit2;
  DW_OP_shl`, that is r31 × 4. Every other register is unchanged.
  Code alignment factor 4, data alignment factor −4.
- **After the sp adjustment**: `DW_CFA_def_cfa_offset` *size*.
- **After the callee-saved stores**: `DW_CFA_offset` for each saved
  register except r31, and for r31 `DW_CFA_val_expression 31:
  DW_OP_lit<n> (or DW_OP_constu n); DW_OP_minus; DW_OP_deref;
  DW_OP_lit2; DW_OP_shl`, where the word is saved at CFA − n. (The CFA is
  on the expression stack when it starts.)
- **With a frame pointer**, once fp is set: `DW_CFA_def_cfa r30, 0`. This
  also covers dynamic allocas and realigned frames, where sp moves.
- Large frames (§8.4) need nothing extra: the rules follow the instruction
  that finishes each step.
- Epilogues have no CFI. The rules are exact at every call and at every
  instruction of the body. They are not exact inside an epilogue, nor for
  up to two instructions where the delay-slot filler moved a prologue
  instruction (a store, or fp = sp + size) into the slots of a later
  branch or call: its rule then starts at the branch. So an asynchronous
  unwinder (a debugger stopping at an arbitrary instruction) may be wrong
  there. CFI never changes the generated code: `-g` and `-g0` give the
  same instructions.

Unwinding one frame: CFA from the rule, then the caller's PC (bytes) from
column 31, then the callee-saved registers from their offsets.

## 9. Pipeline rules for code generators

These rules apply to the dynamic order of execution, including across
taken branches, calls and returns. The compiler (S8, S11) must follow
them, hand-written assembly should, and the simulator (S6) reports every
violation it sees. None of them is checked by the assembler.

### 9.1 Rules

| # | Rule | Source |
|---|---|---|
| P1 | The instruction right after a load must not read the load's destination register, in any operand: Src1, Src2, store data, branch comparison or `jspci` base | Manual §3.2, Table 3-2 (one slot for load–compute, –address, –data and –branch) |
| P2 | A load must not use its destination register as its address register (`ld 0[r4],r4` is illegal) | Manual §3.3 |
| P3 | Every branch and jump is followed by two delay-slot instructions. A delay slot must not hold a branch, jump, `trap`, `jpc`, `jpcrs` or `hsc`. Exception: the slots of `jpc` and `jpcrs`, so that the exception-return sequence `jpcrs; jpc; jpc` is legal | Manual §3.4, §3.5, Appendix VI (Figure VI-2); the manual allows branches in squashed slots, but we do not |
| P4 | After `movtos rX,md`, the next instruction must not be `mstart`, `mstep`, `dstep` or `movfrs md`. Likewise the instruction after an `mstart`, `mstep` or `dstep` must not be `movfrs md` or `movtos rX,md` (conservative) | Manual §3.6.7. The second sentence is stricter than the manual: its division routine (Appendix IV, Figure IV-2) reads `movfrs md` right after the last `dstep`. Routines adapted from the manual need a `nop` there |
| P5 | Memory accesses are naturally aligned (§3) | Manual §2.1 |
| P6 | A store followed by another memory instruction stalls. Performance only, not a correctness rule | Manual §3.3 |
| P7 | Arithmetic must not trap: the start-up code runs with overflow traps masked (§13.3) | Manual §2.4.1 |

What breaking P1 does on the original MIPS-X: the instruction in the
load slot does not see the old register value either. Bypassing hands it
the **address** the load is using instead (manual §3.2). So a P1
violation gives a wrong value, not an old one, which is why the simulator
stops on it rather than modelling it.

If a later test on hardware shows the ES3890 interlocks on loads (plan
L1), P1 can be dropped for that CPU. Whether the ES3890 keeps the
manual's bypass behaviour is likewise unconfirmed.

### 9.2 Hazards at control-flow boundaries

To make P1 checkable within one basic block: **the second delay slot of
any branch or jump must not be a load.** A load may go in the first
delay slot only if the second slot does not read its destination. Then
no load is ever in flight at a branch target, a function entry or a
return point, and the first instruction there can read any register.

A squashing branch that is not taken turns its slots into bubbles, but
they still take a cycle each, so a load before the branch can never form
a load-use pair with the first fall-through instruction. Squashing needs
no extra rule.

P4 has no such rule: a routine may put `mstep`s in its return's delay
slots (`__mulsi3` does), so the first instruction at a return point
must not be `movtos rX,md` or `movfrs md`. The compiler puts a nop
there when its inline multiplication (a `movtos` to MD, then `mstep`s)
follows a call, and never puts `mstart`, `mstep` or `dstep` in a delay
slot itself.

## 10. Assembler syntax

The syntax follows the manual (§4 and Appendix VII), with ES3890
additions. LLVM's generic GNU-style directives are available.

### 10.1 Lexical

- Comments start with `;` and run to the end of the line (as in the
  manual). C-style `/* */` comments are also accepted by LLVM's lexer.
  `#` is not a comment character: it marks immediates.
- Statement separator: `%%` (as AArch64 Darwin uses with a `;` comment
  character). Rarely needed.
- Registers: `r0`–`r31`, case-insensitive, and the aliases `zero`, `at`,
  `cb0`, `cb1`, `gp`, `sp`, `fp`, `ra`. No `$` prefix. The printer always
  writes `rN`.
- Special registers: `psw`, `md`, `pcm4`, `pcm1`.
- Immediate operands of `addi`, `jspci`, shifts and `trap` are written
  with `#`: `#12`, `#-4`, `#%lo(x)`, `#sym+4`. Memory offsets are written
  without `#`: `8[r29]`, `%lo(x)[r2]`, `sym[r0]`. An omitted offset
  (`[r4]`) means 0.
- Labels end with `:`, anywhere on the line. Local labels `1:` / `1f` /
  `1b` and `.L` names work as usual.

### 10.2 Operand order

Sources first, destination last, as in the manual:

| Form | Example |
|---|---|
| Three-register compute | `add r4,r5,r6` (r6 = r4 + r5) |
| Two-register compute | `not r4,r6`; `mstart r5,r6` (Src2, Dest) |
| Shifts | `sh r4,r5,r6,#n`; `asr r4,r6,#n` |
| Immediate | `addi r4,#imm,r6`; `jspci r4,#imm,r31` |
| Load | `ld off[r4],r6` (r6 = memory) |
| Store | `st off[r4],r6` (memory = r6) |
| Branch | `beq r4,r5,label` |
| Specials | `movfrs psw,r6`; `movtos r4,md` |

The shift operand `#n` of `sh` and `asr` is the right-shift amount n, 1
to 32, as in the manual; the encoder computes e = 32 − n (spec §5).

### 10.3 Instructions

All instructions in spec §3–§6:

- Memory (ES3890 feature `es3890`): `ld`, `st`, `ldbu`, `ldb`, `ldhu`,
  `ldh`, `stb`, `sth`. The ES3890 names replace the manual's coprocessor
  and floating-point mnemonics (`ldt`, `stt`, `ldf`, `stf`, `movfrc`,
  `movtoc`, `aluc`), which are not supported. With the generic CPU
  (`-mcpu=mipsx`) only `ld` and `st` exist and the other six encodings
  disassemble as `.word`.
- Branches: `beq bne blt bge blo bhs` and the squashing forms with
  suffix `sq` (`beqsq` …).
- Compute: `add sub subnc and bic not or xor mstart mstep dstep rotlb
  rotlcb sh asr`.
- Compute immediate: `addi jspci movfrs movtos jpc jpcrs hsc trap`.
  `trap #v` takes a vector 0–255.

### 10.4 Delay slots and reordering

**The assembler never fills delay slots, never reorders and never
inserts instructions.** What is written is what is assembled; every
branch and jump must be followed by its two slot instructions in the
source. There is no `.set reorder` mode. The manual's `.noreorg` and
`.reorgon` are not supported.

### 10.5 Pseudo-instructions and aliases

| Pseudo | Expansion | Printed by the disassembler |
|---|---|---|
| `nop` | `add r0,r0,r0` (0x60000019) | Yes |
| `mov rs,rd` | `add rs,r0,rd` | Yes, for any `add` with Src2 = r0 (except `nop`). `add r0,rs,rd` prints as `add` |
| `lsl rs,rd,#k` (k 0–31) | `sh r0,rs,rd,#(32−k)` | Yes, for `sh` with Src1 = r0 |
| `lsr rs,rd,#k` (k 1–32) | `sh rs,r0,rd,#k` | Yes, for `sh` with Src2 = r0 and Src1 ≠ r0 |
| `li #v,rd` | 1, 2 or 3 instructions, chosen by §6.1. `v` must be an absolute expression known when assembling | No |
| `la expr,rd` | Always the 3 instructions of §6.2 with `%hi`/`%lo` | No |
| `b label`, `bra label` | `beq r0,r0,label` | `b` |
| `bsq label` | `beqsq r0,r0,label`. Squashing never happens on an always-taken branch, so this is the same as `b`; it exists because disassemblers print the word | `bsq` |
| `bgt a,b,L`, `ble`, `bhi`, `bls` (and `…sq`) | `blt b,a,L`, `bge b,a,L`, `blo b,a,L`, `bhs b,a,L` | No |
| `call sym` | `jspci r0,#%call(sym),r31` | No |
| `jmp sym` | `jspci r0,#%call(sym),r0` | No |
| `ret` | `jspci r31,#0,r0` | Yes |

Pseudo-instructions do not add delay-slot instructions: `call`, `jmp`,
`ret` and `b` still need two slots written after them. `li` and `la`
write only rd. Every printed alias reassembles to the same word.

### 10.6 Relocation operators

| Operator | Where | Relocation |
|---|---|---|
| `%hi(expr)` | `addi` immediate, memory offset | R_MIPSX_HI17 |
| `%lo(expr)` | `addi` immediate, memory offset | R_MIPSX_LO15 |
| `%gprel(expr)` | `addi` immediate, memory offset | R_MIPSX_GPREL17 |
| `%call(expr)` | `jspci` immediate only | R_MIPSX_CALL17 |
| `%w(expr)` | `addi` or `jspci` immediate | R_MIPSX_WORD17 |
| `%w(expr)` | `.word` / `.long` / `.4byte` | R_MIPSX_32W |
| plain symbolic `expr` | `addi` or `jspci` immediate, memory offset | R_MIPSX_ABS17 |
| label | branch target | R_MIPSX_PC16 |
| constant | branch target | None: the constant is the 16-bit displacement field itself, in words (target word = branch word + 2 + constant) |
| plain `expr` | `.word` / `.long` / `.4byte` | R_MIPSX_32 |
| plain `expr` | `.half` / `.short` / `.2byte` | R_MIPSX_16 |
| plain `expr` | `.byte` | R_MIPSX_8 |
| `expr - .` | `.word` (for example in `.eh_frame`) | R_MIPSX_32_PCREL |

`expr` is a symbol plus or minus a constant. When `expr` is absolute at
assembly time, the operator is evaluated by the assembler and no
relocation is emitted, except for `%call` (an error with a constant) and
`%gprel` (always a relocation).

### 10.7 Directives

Standard LLVM/GNU directives. Points to note:

- `.word` is 32 bits, `.half` / `.short` 16 bits.
- `.align n` means 2ⁿ bytes (as on MIPS); prefer `.p2align` and
  `.balign`.
- Instructions are 32-bit words; `.text` should contain only
  instructions, so that disassembly is clean. Constants go in `.rodata`.

## 11. ELF

### 11.1 Header

| Field | Value |
|---|---|
| `EI_CLASS` | `ELFCLASS32` |
| `EI_DATA` | `ELFDATA2MSB` |
| `EI_OSABI` | `ELFOSABI_NONE` (0) |
| `e_machine` | `EM_MIPS_X` (51, already in LLVM's `ELF.h`) |
| `e_entry` | Byte address of `_start` |
| `e_flags` | See §11.2 |

Relocatable objects use `SHT_RELA` sections (explicit addends); the
linker produces `ET_EXEC` only. Section and symbol conventions are the
generic ELF ones. Symbol values are byte addresses (§4).

### 11.2 `e_flags`

| Flag | Value | Meaning |
|---|---|---|
| `EF_MIPSX_ES3890` | 0x00000001 | Uses the ES3890 byte and halfword loads and stores (spec §3) |
| `EF_MIPSX_VSHIFT` | 0x00000002 | Reserved for the ES3890 variable shift (plan L2), once its encoding is known |
| (others) | | Reserved, must be 0 |

The assembler sets `EF_MIPSX_ES3890` when the subtarget has the `es3890`
feature (the default CPU, `-mcpu=es3890`), whether or not the object uses
those instructions; it is clear for `-mcpu=mipsx`. The linker ORs the
flags of its inputs into the output, and rejects an input with a
reserved bit set. The simulator runs only programs whose flags it
supports.

There is no ABI version field in version 1: there has been only one ABI.
If the ABI changes incompatibly, bits 24–27 become an ABI version (0 =
version 1).

## 12. Relocations

Notation:

- S: the symbol's value (byte address). A: the addend (bytes). P: the
  byte address of the place being relocated (the instruction or data
  word).
- `>>` is arithmetic on signed 32-bit values; `>>>` is logical.
- Fields: **imm17** = bits 16–0 of the instruction word; **disp16** =
  bits 15–0 (bit 16, SQ, is left alone); **src1** = bits 26–22.
- "Signed n" means the value, as a signed 32-bit integer, must be in
  −2ⁿ⁻¹ … 2ⁿ⁻¹ − 1, or the linker reports a range error. "Aligned"
  means the value before shifting must be a multiple of 4, or the linker
  reports an alignment error.

| # | Name | Field | Value | Check | Used for |
|---|---|---|---|---|---|
| 0 | `R_MIPSX_NONE` | — | — | — | |
| 1 | `R_MIPSX_32` | word32 | S + A | — | `.word sym`, function pointers in data |
| 2 | `R_MIPSX_16` | half16 | S + A | Signed or unsigned 16 | `.half sym` |
| 3 | `R_MIPSX_8` | byte8 | S + A | Signed or unsigned 8 | `.byte sym` |
| 4 | `R_MIPSX_32_PCREL` | word32 | S + A − P | — | DWARF and `.eh_frame` |
| 5 | `R_MIPSX_32W` | word32 | (S + A) >>> 2 | Aligned | `.word %w(L)`, jump tables |
| 6 | `R_MIPSX_PC16` | disp16 | ((S + A − P) >> 2) − 2 | Aligned, signed 16 | Branches |
| 7 | `R_MIPSX_CALL17` | imm17 and src1 | See below | Aligned; reachable from a base | `%call`: direct calls and jumps |
| 8 | `R_MIPSX_HI17` | imm17 | (S + A) >> 15 | None needed (always fits) | `%hi` |
| 9 | `R_MIPSX_LO15` | imm17 | (S + A) & 0x7FFF | — | `%lo` |
| 10 | `R_MIPSX_ABS17` | imm17 | S + A | Signed 17 | Plain symbol in an immediate or offset |
| 11 | `R_MIPSX_WORD17` | imm17 | (S + A) >> 2 | Aligned, signed 17 | `%w` in an immediate |
| 12 | `R_MIPSX_GPREL17` | imm17 | S + A − GP | Signed 17 | `%gprel` |

GP is the value of the symbol `_gp`.

**R_MIPSX_CALL17.** Let T = (S + A) >> 2, the target word address (S + A
must be a multiple of 4). For each (register, base) in order (r0, 0),
(r23, `__mipsx_cb0` >> 2), (r24, `__mipsx_cb1` >> 2): if T − base is
signed 17, write T − base to imm17 and the register number to src1, and
stop. If none fits, report an error. The Rdest field (bits 21–17) is not
changed, so the same relocation serves calls (Rdest = r31) and jumps
(Rdest = r0).

**R_MIPSX_PC16.** The target word is P / 4 + 2 + disp, so disp = (S + A
− P) / 4 − 2. Example: a branch at 0x1000 to 0x1010 has disp = 2.

Notes for the implementers:

- **S4 (assembler):** each relocation has a fixup kind of the same name
  (`fixup_mipsx_pc16`, …), with the generic `FK_Data_4/2/1` mapping to
  R_MIPSX_32/16/8 and `FK_Data_4` with PC-relative mapping to
  R_MIPSX_32_PCREL. PC16 to a label in the same section is resolved by
  the assembler; HI17, LO15, ABS17, WORD17 and 32W are resolved when
  their expression is absolute; CALL17 and GPREL17 always produce a
  relocation. Relocations against local symbols may be converted to
  section symbol + addend as usual.
- **S5 (lld):** PC16 is PC-relative (`R_PC`), the rest absolute
  (`R_ABS`), with CALL17 and GPREL17 handled in `relocate()` by looking
  up `__mipsx_cb0`, `__mipsx_cb1` and `_gp`. lld defines those three
  symbols itself when the linker script does not (§13.1).
- **RelocationResolver** (used by DWARF on relocatable objects) needs
  NONE, 32, 16, 8 and 32_PCREL.

## 13. Linking, start-up and the run-time environment

### 13.1 Linker-defined symbols

The default linker scripts (S7) define these. If a script does not, lld
(S5) defines the first three itself with the defaults shown.

| Symbol | Default | Use |
|---|---|---|
| `__mipsx_cb0` | start of `.text` + 0x40000 | Code base 0, byte address (multiple of 4) |
| `__mipsx_cb1` | `__mipsx_cb0` + 0x80000 | Code base 1, byte address (multiple of 4) |
| `_gp` | start of `.sdata` + 0x10000, or of `.data` if there is no `.sdata`, or 0x10000 if neither exists | Global pointer |
| `__stack_top` | top of RAM, 8-byte aligned | Initial sp |
| `__bss_start`, `__bss_end` | | `.bss` and `.sbss` range to clear |
| `__data_load`, `__data_start`, `__data_end` | | `.data` and `.sdata` initial image and destination, if they differ |
| `__init_array_start`, `__init_array_end` | | Constructors |
| `__fini_array_start`, `__fini_array_end` | | Destructors, run by the C library's `exit` (S15) |
| `__heap_start`, `__heap_end` | `_end`, `__stack_top` − 64 KB | The C library's `sbrk` heap (S15) |

Output section order: `.text`, `.rodata`, `.init_array`, `.fini_array`,
`.data`, `.sdata`, `.sbss`, `.bss`, with `.sdata`/`.sbss` together so
`_gp` reaches both.

### 13.2 Memory map

Device (hardware spec): RAM is 0x00000000–0x001FFFFF (2 MB). Exceptions
and interrupts enter at address 0, which must hold a `nop` (manual
Appendix I), and `trap n` enters at word n × 8, byte n × 32. A program
that uses traps keeps 0x0000–0x1FFF for vectors. The device linker
script (S7) decides the rest; the suggested default is `.text` from
0x2000 and `__stack_top` = 0x001FFFF0.

Simulator: the same RAM map, plus the I/O page of §13.5.

### 13.3 Start-up code contract

`_start` (in `crt0.S`, S7) runs first and does, before any call:

1. Set sp = `__stack_top`.
2. Set r23 = `__mipsx_cb0` >> 2, r24 = `__mipsx_cb1` >> 2, r28 = `_gp`
   (each with `la` and, for the bases, `lsr #2`; `la` uses no relocation
   that depends on these registers).
3. Make sure overflow traps are masked (PSW V bit, manual §2.4.1).
   Until the bit's position is confirmed, crt0 relies on the boot
   environment, and the simulator never traps on overflow.
4. Copy `.data`/`.sdata` if their load address differs, clear `.bss`
   and `.sbss`, run `__init_array`.
5. Call `main(0, 0)`, then call `exit` with its result.

### 13.4 Interrupt and exception handlers

Handlers must save every register they change, including r1, r31 and MD,
and the PC chain as the manual describes (Appendix VI). They can reach
memory before setting up a register through r0 (`st off[r0],rX`) in the
lowest or highest 64 KB. They never need to save r23, r24 or r28. The
manual's rule that no register may be accessed in the first two
instructions of a handler (Appendix I, item 3) applies.

### 13.5 Simulator I/O page

A simulator-only page at 0xFFFF0000–0xFFFF00FF, reachable from r0 in one
instruction (`st -0x10000[r0],r4`). S6 owns this layout and may extend
it; this is the starting point:

| Address | Offset from r0 | Access | Function |
|---|---|---|---|
| 0xFFFF0000 | −65536 | Store (any width) | Write the low 8 bits to stdout |
| 0xFFFF0004 | −65532 | Store word | Exit with the stored value as status |
| 0xFFFF0008 | −65528 | Load word | Cycle counter, low word (latches the high word) |
| 0xFFFF000C | −65524 | Load word | Cycle counter, high word, as latched |
| 0xFFFF0010 | −65520 | Load word | Read a byte from stdin, or −1 at end of file |
| 0xFFFF0014 | −65516 | Store (any width) | Write the low 8 bits to stderr (simulator extension) |
| 0xFFFF0018 | −65512 | Load word | Instructions executed, low word (latches the high word; simulator extension) |
| 0xFFFF001C | −65508 | Load word | Instructions executed, high word, as latched (simulator extension) |

The exit status is the low 8 bits of the stored word, as for a host
process. Any other access is a simulation error: a load narrower than a
word, an exit store narrower than a word, a store to a load-only register
or a load from a store-only one, and any other offset in the page.
`sim/README.md` is the reference for the simulator's behaviour.

### 13.6 Atomics and synchronisation

There are no atomic instructions (manual Appendix I, item 4) and one CPU.
Clang (S13) sets the maximum inline atomic width to 0 and the backend
(S14) runs LLVM's AtomicExpand, so `__atomic_*` and `__sync_*` operations
become calls to libatomic-style functions (`__atomic_load_4`,
`__atomic_fetch_add_2`, `__atomic_compare_exchange_8`, the generic
`__atomic_load` and so on). `rt/atomic.c` in `libbuiltins.a` implements
them by setting the PSW M bit (the interrupt mask) around a plain access
and restoring the PSW afterwards; every memory order is treated as `seq_cst`. The bit position
comes from the manual and is unconfirmed for the ES3890 (§2.3), and in
user state `movtos psw` does nothing, so there the functions are atomic
only with respect to code that is not an interrupt handler. A fence emits
no instruction: it is a compiler barrier, since memory accesses complete
in order.

### 13.7 `setjmp` and `longjmp`

`jmp_buf` holds r16–r22, r25–r27, r29, r30 and r31, in that order: 13
words (S15; picolibc's `_JBLEN`). r23, r24 and r28 never change after
start-up, so they are not saved.

## 14. Decisions and rationale

Each decision lists what was chosen, why, and the alternatives rejected.

**D1. Register map (§2).** Arguments r4–r11, return r2/r3, sp r29, ra
r31, code bases r23/r24 and callee-saved r16–r22 keep the stock
firmware's layout (spec §7), which makes our binaries look familiar
beside the vendor's analysis and costs nothing. Eight argument registers
rather than MIPS o32's four, because MIPS-X has no multi-register
store, so stack arguments are expensive, and 32 registers leave plenty.
r1 is the scratch register because late expansions (long calls, large
frames) otherwise need the register scavenger. r25–r27 and r30 are added
to the callee-saved set to balance the split at 14 caller-saved and 11
callee-saved. Rejected: MIPS o32's four argument registers (too few for
no-cost calls on a machine with no load/store multiple); reserving
kernel registers like MIPS k0/k1 (handlers can store through r0 to
fixed low addresses instead, §13.4); no reserved scratch (more work in
S10 for no measurable gain).

**D2. Function pointers are byte addresses (§4).** This keeps C pointer
arithmetic, comparisons, casts to `uintptr_t`, `memcpy` of pointers and
null checks normal, and makes every symbol value and `R_MIPSX_32` a byte
address, which is what lld and the MC layer assume. The cost is one
shift before each indirect call. Rejected: word-address function
pointers (saves the shift, but pointers to functions and data would have
different units, `(char *)f + 4` would mean something else, and tools
like `llvm-objdump` and DWARF expect byte addresses); AVR-style
`pm()`/`gs()` wrappers in C (needed on AVR because its program memory is
a separate address space; ours is not).

**D3. Direct calls go through a linker-selected code base (§5.2); this
answers plan question L3 together with D2.** One instruction per call,
like the stock firmware, with no veneers and no scratch register. The
linker picks r0, r23 or r24 by rewriting the Src1 field, so the compiler
never needs to know where a function will end up. Three bases reach at
least 1 MB of code, and the stack plan's worst-case estimate for code is
about 0.75 MB (stack plan §3.4). `-mlong-calls` covers anything bigger.
Rejected: one base register only (512 KB is below the worst-case
estimate); compiler-chosen bases (the compiler cannot know which base
reaches a function in another file); linker thunks or veneers for
out-of-range calls (more complex in lld, needs a scratch register in the
thunk, slower calls); always using the long-call sequence (five
instructions per call instead of one, which code size cannot afford).

**D4. No branch relaxation in the assembler; the code generator relaxes
far branches (§5.5).** The assembler's output is exactly its input, which
matches the rule that delay slots are explicit and keeps S3/S4 simple.
Functions larger than 128 KB will be rare. Rejected: assembler
relaxation (would have to invent delay-slot instructions); linker
relaxation (no need).

**D5. 32-bit constants and addresses use addi / lsl 15 / addi with an
unsigned 15-bit low part (§6).** Any value takes at most three
instructions, no memory access and no load delay, and `%lo` can be a
load offset with no carry correction because it is never negative.
Rejected: a 17-bit signed low part with a rounding `%hi` (the same
length, but needs the `+0x10000` rounding everywhere, like MIPS `%hi`);
a literal pool (one instruction and a word of data, 8 bytes against 12,
but adds a load delay and a base register; can be added later as an
optimisation using `.sdata` and `%gprel`, with no ABI change); the
manual's `ld #exp,reg` syntax that builds a pool (needs the assembler to
manage pools).

**D6. Reserve gp and set it up from version 1, but leave its use
optional (§6.3).** Reserving it now means objects built before and after
small-data support can be mixed. Rejected: no gp (globals would always
cost three instructions plus the access, and adding gp later would
change the register map); requiring small data in S9 (more work before
there is a working compiler).

**D7. Arguments are a stream of words (§7.1).** Registers are used in
order, a two-word value may straddle r11 and the stack, and there is no
alignment padding. This is what LLVM's type legaliser produces with a
plain register list, so `CallingConv.td` stays simple, and with no
64-bit loads there is no reason to align 64-bit values in registers or
on the stack. The caller extends narrow arguments and the callee extends
narrow return values, as on MIPS and RISC-V, so neither has to
re-extend. Rejected: even-register pairs for 64-bit values (MIPS o32;
wastes registers for no gain here); "a value that does not fit goes
wholly on the stack" (needs custom calling-convention code).

**D8. Variadic arguments always go on the stack (§7.2).** `va_list` is a
plain pointer, `va_arg` is a pointer bump, and variadic functions need no
register save area, which makes S10 and S13 much simpler. The cost falls
only on variadic calls such as `printf`, which are not hot. Rejected:
passing variadic arguments in registers with a save area in the callee
(the usual SysV way; more code in the backend and in every variadic
prologue, and `va_arg` becomes complicated when 64-bit values straddle
registers and stack).

**D9. Aggregates up to 16 bytes are passed in words; larger ones by
reference to a caller-made copy. Aggregates up to 8 bytes are returned in
r2/r3; larger ones through a hidden pointer in r4 (§7.1, §7.3).** Small
structs (pairs, small descriptors) go in registers at no cost; large
ones avoid a big copy into the argument area. Passing a pointer to a
copy avoids `byval` lowering in the backend. The callee does not return
the hidden pointer, which saves work in `LowerReturn`. Rejected: `byval`
on the stack (more backend work, and big copies into the outgoing area);
returning the sret pointer in r2 (MIPS and x86 do; nothing here needs
it).

**D10. 64-bit values: most significant word first, in registers as in
memory; 8-byte alignment in memory, 4 on the stack (§3, §7.1).** The
register order matches big-endian memory order, which LLVM produces for
a big-endian target anyway, and makes spilling a pair a plain copy.
8-byte alignment of `long long` and `double` in structs matches what
portable code expects (lwIP, BearSSL and picolibc are tested on such
targets). Rejected: 4-byte alignment in memory (saves a few bytes of
padding but differs from every common 32-bit ABI).

**D11. `char` is signed (§3).** As on MIPS, where MIPS-X comes from, and
as in GCC's default for most embedded C. The ES3890 has both loads
(spec §3), so neither choice costs instructions. (The signedness of the
two byte loads is still a Hypothesis in the spec; whichever turns out to
be which, the compiler uses the right one.) Rejected: unsigned `char` (as
on ARM; no advantage here).

**D12. Assembler syntax as in the manual, with no delay-slot filling
(§10).** Source-first, destination-last operands, `#` immediates and
`off[reg]` addressing match the manual, so its examples assemble. `;`
comments as in the manual. The assembler never fills slots or reorders,
as the plan recommends: the compiler's slot filler (S11) is the only
place that moves instructions. Rejected: MIPS-style destination-first
syntax (would contradict every manual example); a reorganising assembler
(like the original Stanford tools; hard to test and makes disassembly
differ from source).

**D13. ELF: RELA, byte-valued symbols, one extension flag (§11, §12).**
RELA keeps the addend out of the 16- and 17-bit fields and is what most
LLVM targets use. All conversions to words happen inside relocations, so
the rest of the toolchain sees only byte addresses (the AVR approach).
Rejected: REL (addends limited by the field widths); word-valued code
symbols as in the manual (every tool would need to know about them).

**D14. Simulator I/O page at 0xFFFF0000 (§13.5).** The top 64 KB of the
address space is reachable from r0 with a negative offset, so `putchar`
is one store, and it cannot collide with RAM or the device's I/O seen so
far (0x14000000, 0x1CFEFFFC). Rejected: an address in the middle of the
space (needs a three-instruction address); a trap-based interface (traps
are for the operating system later).

**D15. Return addresses stay word addresses; only
`__builtin_return_address` converts (§4).** `jspci` produces a word
address, and converting at every call would cost an instruction. Code
that looks at return addresses is rare. For DWARF unwinding (S17), the
rule for return address column 31 is a `DW_CFA_val_expression` that
multiplies by 4 (§8.6), so the unwind tables are self-describing and a
standard unwinder needs no MIPS-X knowledge. Rejected: leaving the ×4 to
the consumer (every tool would need to know, and silently wrong
otherwise); a separate pseudo-register column for the byte return address
(an extra register number in every tool, for no gain: r31 is clobbered by
the call, so its recovered value in the caller does not matter); word
addresses in DWARF (would disagree with ELF symbols, §4).

**D16. Jump-table entries are word addresses (§5.6).** Saves one
instruction per switch dispatch. The tables are private to the compiler,
so D2's reasoning does not apply. Rejected: byte entries (one more
instruction); PC-relative entries (no PC-relative jump exists, so they
would cost more).

**D17. Hazard rule at control-flow boundaries (§9.2).** Forbidding a load
in the second delay slot lets every pass, and the simulator's reports,
reason about load delays one block at a time, at the cost of a few
filling opportunities in S11. Rejected: tracking pending loads across
edges (needs whole-function analysis, and calls and returns cross
compilation units).

## 15. Questions each work package may ask

| Package | Question | Answer |
|---|---|---|
| S2 | Register classes? | GPR = r0–r31 (with r0 constant); specials psw, md, pcm4/pcm1 (§2) |
| S2 | Subtarget features and CPUs? | Feature `es3890` (byte/halfword memory ops); feature `long-calls`; CPUs `es3890` (default, has `es3890`) and `mipsx` (§10.3, §5.4) |
| S2 | Printer conventions? | `rN` names, manual operand order, aliases of §10.5 |
| S2 | Comment and separator strings? | `;` and `%%` (§10.1) |
| S3 | Immediate ranges? | imm17 −65536…65535; disp16 in words; `sh`/`asr` n 1–32; `lsl` 0–31; `lsr` 1–32; `trap` 0–255 |
| S3 | Pseudo expansions? | §10.5 and §6.1 |
| S3 | Memory operand syntax? | `off[reg]`, `[reg]` (§10.1) |
| S4 | Fixups, relocation numbers, formulas? | §12 |
| S4 | `e_flags`? | §11.2 |
| S4 | REL or RELA? | RELA |
| S5 | Range checks, code base symbols, `_gp`? | §12, §13.1 |
| S6 | Hazards to report? | P1–P5 and §9.2 (§9) |
| S6 | Return address value of `jspci`? | Its word address + 3 (§5.1) |
| S6 | I/O page? | §13.5 |
| S7 | crt0 duties, linker symbols, memory map? | §13 |
| S8 | Calling convention, callee-saved set, reserved registers? | §2.1, §7 |
| S8 | Data layout? | `E-m:e-p:32:32-i64:64-n32-S64` (§3) |
| S8 | Stack alignment, frame layout? | 8 bytes, §8 |
| S9 | Constants, global addresses, small data? | §6 |
| S9 | Jump tables? | Word entries, R_MIPSX_32W (§5.6) |
| S9 | Far branches? | §5.5 |
| S10 | Indirect calls? | Shift right 2, `jspci rT,#0,r31` (§5.6) |
| S10 | Varargs? | Stack only, `va_list` = `char *` (§7.2) |
| S10 | Struct arguments and returns? | §7.1, §7.3 |
| S10 | Large frames, frame pointer, alloca? | §8.2–§8.4 |
| S10 | i64 order? | High word first (§7.1) |
| S12 | Helper convention? | Standard (§7.4) |
| S13 | Type sizes, `char` signedness, `va_list`, atomics? | §3, §7.2, §13.6 |
| S17 | DWARF numbers, return address unit, DWARF addresses? | §2.4, §4, §8.6, D15 |
