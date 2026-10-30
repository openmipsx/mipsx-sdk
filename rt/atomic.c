/* Atomic operations for a single MIPS-X CPU (abi.md section 13.6).
 * SPDX-License-Identifier: Apache-2.0
 *
 * MIPS-X has no atomic instructions and the ES3890 has one CPU, so Clang
 * and the backend turn every atomic operation into a call to one of the
 * libatomic-style functions below. Each one runs with interrupts masked:
 * it sets the PSW M bit, the interrupt mask (bit 4, 0x10: the manual's
 * Figure 2-3 and section 2.4, and the processor spec's section 10 for the
 * ES3890), and restores the old PSW afterwards. (The I bit, bit 2, only
 * records whether the last exception was an interrupt; like the rest of
 * the PSW layout it is not confirmed for the ES3890, abi.md section 2.3.)
 * In user state `movtos psw` does nothing, so there the functions are
 * plain loads and stores; that is still atomic with respect to other code
 * on this CPU unless an interrupt handler touches the same object.
 *
 * Every memory order is treated as seq_cst: the CPU does not reorder
 * memory accesses, and the calls are compiler barriers.
 *
 * The names are the ones LLVM's AtomicExpand pass and Clang call (as in
 * GCC's libatomic). Several are also Clang builtins, so the C functions
 * get their symbol names from asm labels.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PSW_M 0x10u /* interrupt mask */

static inline unsigned irq_save(void) {
  unsigned psw;
  __asm__ volatile("movfrs psw,%0" : "=r"(psw)::"memory");
  __asm__ volatile("movtos %0,psw" ::"r"(psw | PSW_M) : "memory");
  return psw;
}

static inline void irq_restore(unsigned psw) {
  __asm__ volatile("movtos %0,psw" ::"r"(psw) : "memory");
}

static void copy(volatile unsigned char *d, const volatile unsigned char *s,
                 size_t n) {
  while (n--)
    *d++ = *s++;
}

static int compare(const volatile unsigned char *a,
                   const volatile unsigned char *b, size_t n) {
  for (; n; --n, ++a, ++b)
    if (*a != *b)
      return 1;
  return 0;
}

/* Generic (any size) versions. */

void atomic_load_any(size_t n, const volatile void *src, void *dst,
                     int order) __asm__("__atomic_load");
void atomic_load_any(size_t n, const volatile void *src, void *dst,
                     int order) {
  (void)order;
  unsigned psw = irq_save();
  copy(dst, src, n);
  irq_restore(psw);
}

void atomic_store_any(size_t n, volatile void *dst, void *src,
                      int order) __asm__("__atomic_store");
void atomic_store_any(size_t n, volatile void *dst, void *src, int order) {
  (void)order;
  unsigned psw = irq_save();
  copy(dst, src, n);
  irq_restore(psw);
}

void atomic_exchange_any(size_t n, volatile void *ptr, void *val, void *old,
                         int order) __asm__("__atomic_exchange");
void atomic_exchange_any(size_t n, volatile void *ptr, void *val, void *old,
                         int order) {
  (void)order;
  unsigned psw = irq_save();
  copy(old, ptr, n);
  copy(ptr, val, n);
  irq_restore(psw);
}

bool atomic_compare_exchange_any(size_t n, volatile void *ptr, void *expected,
                                 void *desired, int success,
                                 int failure) __asm__("__atomic_compare_exchange");
bool atomic_compare_exchange_any(size_t n, volatile void *ptr, void *expected,
                                 void *desired, int success, int failure) {
  (void)success;
  (void)failure;
  unsigned psw = irq_save();
  bool equal = !compare(ptr, expected, n);
  if (equal)
    copy(ptr, desired, n);
  else
    copy(expected, ptr, n);
  irq_restore(psw);
  return equal;
}

bool atomic_is_lock_free(size_t n, const volatile void *ptr) __asm__(
    "__atomic_is_lock_free");
bool atomic_is_lock_free(size_t n, const volatile void *ptr) {
  (void)n;
  (void)ptr;
  return false;
}

/* Sized versions: __atomic_load_N and so on, N = 1, 2, 4, 8. */

#define SIZED(N, T)                                                            \
  T atomic_load_##N(const volatile T *p, int o) __asm__("__atomic_load_" #N);  \
  T atomic_load_##N(const volatile T *p, int o) {                              \
    (void)o;                                                                   \
    unsigned psw = irq_save();                                                 \
    T v = *p;                                                                  \
    irq_restore(psw);                                                          \
    return v;                                                                  \
  }                                                                            \
  void atomic_store_##N(volatile T *p, T v, int o) __asm__(                    \
      "__atomic_store_" #N);                                                   \
  void atomic_store_##N(volatile T *p, T v, int o) {                           \
    (void)o;                                                                   \
    unsigned psw = irq_save();                                                 \
    *p = v;                                                                    \
    irq_restore(psw);                                                          \
  }                                                                            \
  T atomic_exchange_##N(volatile T *p, T v, int o) __asm__(                    \
      "__atomic_exchange_" #N);                                                \
  T atomic_exchange_##N(volatile T *p, T v, int o) {                           \
    (void)o;                                                                   \
    unsigned psw = irq_save();                                                 \
    T old = *p;                                                                \
    *p = v;                                                                    \
    irq_restore(psw);                                                          \
    return old;                                                                \
  }                                                                            \
  bool atomic_compare_exchange_##N(volatile T *p, T *e, T d, int s, int f)     \
      __asm__("__atomic_compare_exchange_" #N);                                \
  bool atomic_compare_exchange_##N(volatile T *p, T *e, T d, int s, int f) {   \
    (void)s;                                                                   \
    (void)f;                                                                   \
    unsigned psw = irq_save();                                                 \
    T old = *p;                                                                \
    bool equal = old == *e;                                                    \
    if (equal)                                                                 \
      *p = d;                                                                  \
    else                                                                       \
      *e = old;                                                                \
    irq_restore(psw);                                                          \
    return equal;                                                              \
  }                                                                            \
  RMW(N, T, add, old + v)                                                      \
  RMW(N, T, sub, old - v)                                                      \
  RMW(N, T, and, old & v)                                                      \
  RMW(N, T, or, old | v)                                                       \
  RMW(N, T, xor, old ^ v)                                                      \
  RMW(N, T, nand, ~(old & v))

/* __atomic_fetch_OP_N returns the old value, __atomic_OP_fetch_N the new. */
#define RMW(N, T, OP, EXPR)                                                    \
  T atomic_fetch_##OP##_##N(volatile T *p, T v, int o) __asm__(                \
      "__atomic_fetch_" #OP "_" #N);                                           \
  T atomic_fetch_##OP##_##N(volatile T *p, T v, int o) {                       \
    (void)o;                                                                   \
    unsigned psw = irq_save();                                                 \
    T old = *p;                                                                \
    *p = (EXPR);                                                               \
    irq_restore(psw);                                                          \
    return old;                                                                \
  }                                                                            \
  T atomic_##OP##_fetch_##N(volatile T *p, T v, int o) __asm__(                \
      "__atomic_" #OP "_fetch_" #N);                                           \
  T atomic_##OP##_fetch_##N(volatile T *p, T v, int o) {                       \
    (void)o;                                                                   \
    unsigned psw = irq_save();                                                 \
    T old = *p;                                                                \
    T new = (EXPR);                                                            \
    *p = new;                                                                  \
    irq_restore(psw);                                                          \
    return new;                                                                \
  }

SIZED(1, uint8_t)
SIZED(2, uint16_t)
SIZED(4, uint32_t)
SIZED(8, uint64_t)

/* GCC's full barrier; the backend never calls it (fences are compiler
 * barriers), but code may. */
void sync_synchronize(void) __asm__("__sync_synchronize");
void sync_synchronize(void) { __asm__ volatile("" ::: "memory"); }
