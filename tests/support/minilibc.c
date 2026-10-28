/* Minimal C library for the SDK's execution tests (tests/README.md).
 * SPDX-License-Identifier: Apache-2.0
 *
 * Just enough for the compiler-rt builtins tests and the GCC C torture
 * tests to link and report: output through the simulator's I/O page
 * (abi.md section 13.5), a bump allocator, the string functions Clang may
 * call. Not a libc: S15 brings picolibc.
 */
#include <ctype.h>
#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define IO_STDOUT ((volatile unsigned *)0xFFFF0000)
#define IO_EXIT ((volatile unsigned *)0xFFFF0004)
#define IO_STDIN ((volatile int *)0xFFFF0010)
#define IO_STDERR ((volatile unsigned *)0xFFFF0014)

struct _mini_FILE {
  int fd;
};
static struct _mini_FILE files[3] = {{0}, {1}, {2}};
FILE *const stdin = &files[0], *const stdout = &files[1],
            *const stderr = &files[2];

_Noreturn void _exit(int status) {
  for (;;)
    *IO_EXIT = (unsigned)status;
}
_Noreturn void exit(int status) { _exit(status); }
_Noreturn void abort(void) { _exit(134); }
void __mini_assert(const char *e, const char *file, int line) {
  fprintf(stderr, "%s:%d: assertion failed: %s\n", file, line, e);
  abort();
}

int fputc(int c, FILE *f) {
  if (f->fd == 2)
    *IO_STDERR = (unsigned char)c;
  else
    *IO_STDOUT = (unsigned char)c;
  return (unsigned char)c;
}
int putc(int c, FILE *f) { return fputc(c, f); }
int putchar(int c) { return fputc(c, stdout); }
int fputs(const char *s, FILE *f) {
  while (*s)
    fputc(*s++, f);
  return 0;
}
int puts(const char *s) {
  fputs(s, stdout);
  putchar('\n');
  return 0;
}
size_t fwrite(const void *p, size_t size, size_t n, FILE *f) {
  const unsigned char *c = p;
  for (size_t i = 0; i < size * n; ++i)
    fputc(c[i], f);
  return n;
}
int fflush(FILE *f) {
  (void)f;
  return 0;
}
int getchar(void) { return *IO_STDIN; }

/* printf: d i u x X o c s p, flags - 0 + space #, width, precision,
 * h hh l ll z j t. Floating point is printed as %a-style hex bits. */
struct out {
  char *buf;
  size_t size, len;
  FILE *f;
};
static void emit(struct out *o, char c) {
  if (o->f)
    fputc(c, o->f);
  else if (o->len + 1 < o->size)
    o->buf[o->len] = c;
  o->len++;
}
/* Floating point: exact for values that fit in 64-bit integers after
 * scaling, close enough otherwise. %a prints the bits in hex. */
static double floor_(double x) { /* x >= 0 */
  if (x >= 4503599627370496.0)
    return x;
  return (double)(unsigned long long)x;
}
static int fmt_digits(char *o, double x, int prec, int alt) {
  /* x >= 0, finite: integer part, then prec fraction digits, rounded. */
  double scale = 1;
  for (int i = 0; i < prec; ++i)
    scale *= 10;
  char *s = o;
  char r[400];
  int k = 0;
  if (x * scale < 9.2e18) {
    unsigned long long v = (unsigned long long)(x * scale + 0.5);
    if ((double)v - x * scale == 0.5 && (v & 1))
      v--; /* round half to even */
    for (int i = 0; i < prec || v; ++i) {
      r[k++] = '0' + v % 10;
      v /= 10;
      if (i + 1 == prec)
        r[k++] = '.';
    }
    if (prec && r[k - 1] == '.')
      r[k++] = '0';
    if (!k)
      r[k++] = '0';
  } else {
    double ip = x;
    for (int i = 0; i < prec; ++i)
      r[k++] = '0';
    if (prec)
      r[k++] = '.';
    do {
      double q = floor_(ip / 10);
      r[k++] = '0' + (int)(ip - q * 10);
      ip = q;
    } while (ip >= 1 && k < 380);
  }
  while (k)
    *s++ = r[--k];
  if (alt && !prec)
    *s++ = '.';
  return (int)(s - o);
}
static int fmt_float(char *o, double x, char conv, int prec, int plus,
                     int space, int alt) {
  char *s = o;
  int upper = conv >= 'A' && conv <= 'Z';
  conv |= 32;
  if (__builtin_signbit(x)) {
    *s++ = '-';
    x = -x;
  } else if (plus)
    *s++ = '+';
  else if (space)
    *s++ = ' ';
  if (x != x || x == __builtin_inf()) {
    const char *t = x != x ? (upper ? "NAN" : "nan") : (upper ? "INF" : "inf");
    while (*t)
      *s++ = *t++;
    return (int)(s - o);
  }
  if (conv == 'a') {
    union { double d; unsigned long long u; } b = {x};
    static const char *hex = "0123456789abcdef";
    *s++ = '0'; *s++ = 'x';
    for (int i = 60; i >= 0; i -= 4) *s++ = hex[(b.u >> i) & 15];
    return (int)(s - o);
  }
  if (prec < 0)
    prec = 6;
  int e = 0;
  if (conv != 'f' && x != 0) {
    while (x >= 10) { x /= 10; ++e; }
    while (x < 1) { x *= 10; --e; }
  }
  if (conv == 'g') {
    int p = prec ? prec : 1;
    /* Rounding to p digits may carry into a new digit. */
    double sc = x, r = 0.5;
    for (int i = 1; i < p; ++i) r /= 10;
    if (sc + r >= 10) { ++e; x /= 10; }
    if (e < -4 || e >= p) {
      conv = 'e';
      prec = p - 1;
    } else {
      conv = 'f';
      for (int i = 0; i < e; ++i) x *= 10;
      for (int i = 0; i > e; --i) x /= 10;
      prec = p - 1 - e;
    }
    char *start = s;
    s += fmt_digits(s, x, prec, alt);
    if (!alt) {
      char *dot = 0;
      for (char *q = start; q < s; ++q) if (*q == '.') dot = q;
      if (dot) {
        while (s[-1] == '0') --s;
        if (s[-1] == '.') --s;
      }
    }
    if (conv == 'e') goto exponent;
    return (int)(s - o);
  }
  if (conv == 'e') {
    double r = 0.5;
    for (int i = 0; i < prec; ++i) r /= 10;
    if (x + r >= 10) { x /= 10; ++e; }
    s += fmt_digits(s, x, prec, alt);
  exponent:
    *s++ = upper ? 'E' : 'e';
    *s++ = e < 0 ? '-' : '+';
    if (e < 0) e = -e;
    if (e >= 100) *s++ = '0' + e / 100;
    *s++ = '0' + e / 10 % 10;
    *s++ = '0' + e % 10;
    return (int)(s - o);
  }
  s += fmt_digits(s, x, prec, alt);
  return (int)(s - o);
}

static int vfprintf_impl(struct out *o, const char *fmt, va_list ap) {
  for (; *fmt; ++fmt) {
    if (*fmt != '%') {
      emit(o, *fmt);
      continue;
    }
    int left = 0, zero = 0, plus = 0, space = 0, alt = 0, width = 0,
        prec = -1, lng = 0, half = 0;
    for (;; ++fmt) {
      char c = fmt[1];
      if (c == '-') left = 1;
      else if (c == '0') zero = 1;
      else if (c == '+') plus = 1;
      else if (c == ' ') space = 1;
      else if (c == '#') alt = 1;
      else break;
    }
    ++fmt;
    if (*fmt == '*') {
      width = va_arg(ap, int);
      ++fmt;
    } else
      while (*fmt >= '0' && *fmt <= '9')
        width = width * 10 + *fmt++ - '0';
    if (*fmt == '.') {
      prec = 0;
      ++fmt;
      if (*fmt == '*') {
        prec = va_arg(ap, int);
        ++fmt;
      } else
        while (*fmt >= '0' && *fmt <= '9')
          prec = prec * 10 + *fmt++ - '0';
    }
    for (;; ++fmt) {
      if (*fmt == 'l') lng++;
      else if (*fmt == 'h') half++;
      else if (*fmt == 'z' || *fmt == 'j' || *fmt == 't')
        lng = *fmt == 'j' ? 2 : 1;
      else if (*fmt == 'L') lng = 3;
      else break;
    }
    char tmp[420], *s = tmp;
    int n = 0, neg = 0;
    unsigned long long v = 0;
    char conv = *fmt;
    switch (conv) {
    case 'd':
    case 'i': {
      long long x = lng >= 2 ? va_arg(ap, long long)
                    : lng ? va_arg(ap, long) : va_arg(ap, int);
      if (half == 1) x = (short)x;
      if (half >= 2) x = (signed char)x;
      neg = x < 0;
      v = neg ? -(unsigned long long)x : (unsigned long long)x;
      goto number;
    }
    case 'u': case 'x': case 'X': case 'o': case 'p':
      if (conv == 'p') {
        v = (uintptr_t)va_arg(ap, void *);
        alt = 1;
      } else
        v = lng >= 2 ? va_arg(ap, unsigned long long)
            : lng ? va_arg(ap, unsigned long) : va_arg(ap, unsigned);
      if (half == 1) v = (unsigned short)v;
      if (half >= 2) v = (unsigned char)v;
    number: {
      unsigned base = conv == 'o' ? 8 : (conv == 'x' || conv == 'X' || conv == 'p') ? 16 : 10;
      const char *dig = conv == 'X' ? "0123456789ABCDEF" : "0123456789abcdef";
      char r[24];
      int k = 0;
      do {
        r[k++] = dig[v % base];
        v /= base;
      } while (v);
      if (neg) *s++ = '-';
      else if (plus) *s++ = '+';
      else if (space) *s++ = ' ';
      if (alt && base == 16 && (r[0] != '0' || k > 1 || conv == 'p')) {
        *s++ = '0'; *s++ = conv == 'X' ? 'X' : 'x';
      }
      if (alt && base == 8 && r[k - 1] != '0' && prec <= k) prec = k + 1;
      for (int z = k; z < prec; ++z) *s++ = '0';
      if (zero && !left && prec < 0) {
        int have = (int)(s - tmp) + k;
        char *p = tmp + (neg || plus || space) + (alt && base == 16) * 2;
        for (; have < width; ++have) {
          memmove(p + 1, p, s - p);
          *p = '0';
          ++s;
        }
      }
      while (k) *s++ = r[--k];
      n = (int)(s - tmp);
      s = tmp;
      break;
    }
    case 'c':
      tmp[0] = (char)va_arg(ap, int);
      n = 1;
      break;
    case 's':
      s = va_arg(ap, char *);
      if (!s) s = "(null)";
      n = (int)strlen(s);
      if (prec >= 0 && n > prec) n = prec;
      break;
    case 'f': case 'F': case 'e': case 'E': case 'g': case 'G': case 'a': case 'A':
      n = fmt_float(tmp, va_arg(ap, double), conv, prec, plus, space, alt);
      if (zero && !left)
        for (; n < width && n < (int)sizeof tmp - 1; ++n) {
          int at = tmp[0] == '-' || tmp[0] == '+' || tmp[0] == ' ';
          memmove(tmp + at + 1, tmp + at, n - at);
          tmp[at] = '0';
        }
      s = tmp;
      break;
    case '%':
      tmp[0] = '%';
      n = 1;
      break;
    case 'n':
      *va_arg(ap, int *) = (int)o->len;
      continue;
    default:
      return -1;
    }
    if (!left) for (int p = n; p < width; ++p) emit(o, ' ');
    for (int i = 0; i < n; ++i) emit(o, s[i]);
    if (left) for (int p = n; p < width; ++p) emit(o, ' ');
  }
  return (int)o->len;
}
int vfprintf(FILE *f, const char *fmt, va_list ap) {
  struct out o = {0, 0, 0, f};
  return vfprintf_impl(&o, fmt, ap);
}
int vsnprintf(char *buf, size_t size, const char *fmt, va_list ap) {
  struct out o = {buf, size, 0, 0};
  int r = vfprintf_impl(&o, fmt, ap);
  if (size)
    buf[o.len < size ? o.len : size - 1] = 0;
  return r;
}
int vsprintf(char *buf, const char *fmt, va_list ap) {
  return vsnprintf(buf, (size_t)-1 >> 1, fmt, ap);
}
int vprintf(const char *fmt, va_list ap) { return vfprintf(stdout, fmt, ap); }
#define VA(call)                                                               \
  va_list ap;                                                                  \
  va_start(ap, fmt);                                                           \
  int r = call;                                                                \
  va_end(ap);                                                                  \
  return r
int printf(const char *fmt, ...) { VA(vfprintf(stdout, fmt, ap)); }
int fprintf(FILE *f, const char *fmt, ...) { VA(vfprintf(f, fmt, ap)); }
int sprintf(char *b, const char *fmt, ...) { VA(vsprintf(b, fmt, ap)); }
int snprintf(char *b, size_t n, const char *fmt, ...) {
  VA(vsnprintf(b, n, fmt, ap));
}

/* Memory: a bump allocator from _end up to 64 KB below the top of the
 * stack (sim.ld); free does nothing. */
extern unsigned char _end[], __stack_top[];
static unsigned char *brk_;
void *malloc(size_t n) {
  if (!brk_)
    brk_ = (unsigned char *)(((uintptr_t)_end + 7) & ~(uintptr_t)7);
  n = (n + 15) & ~(size_t)7;
  if (n > (size_t)(__stack_top - 0x10000 - brk_))
    return 0;
  unsigned char *p = brk_;
  brk_ += n;
  *(size_t *)p = n - 8;
  return p + 8;
}
void free(void *p) { (void)p; }
void *calloc(size_t a, size_t b) {
  void *p = malloc(a * b);
  if (p)
    memset(p, 0, a * b);
  return p;
}
void *realloc(void *old, size_t n) {
  void *p = malloc(n);
  if (p && old) {
    size_t had = *(size_t *)((unsigned char *)old - 8);
    memcpy(p, old, had < n ? had : n);
  }
  return p;
}

/* Strings. Built with -fno-builtin so Clang does not turn the loops back
 * into calls to themselves. */
void *memcpy(void *d, const void *s, size_t n) {
  unsigned char *dp = d;
  const unsigned char *sp = s;
  while (n--)
    *dp++ = *sp++;
  return d;
}
void *memmove(void *d, const void *s, size_t n) {
  unsigned char *dp = d;
  const unsigned char *sp = s;
  if (dp < sp)
    while (n--)
      *dp++ = *sp++;
  else
    while (n--)
      dp[n] = sp[n];
  return d;
}
void *memset(void *d, int c, size_t n) {
  unsigned char *dp = d;
  while (n--)
    *dp++ = (unsigned char)c;
  return d;
}
int memcmp(const void *a, const void *b, size_t n) {
  const unsigned char *x = a, *y = b;
  for (; n; --n, ++x, ++y)
    if (*x != *y)
      return *x - *y;
  return 0;
}
void *memchr(const void *s, int c, size_t n) {
  const unsigned char *p = s;
  for (; n; --n, ++p)
    if (*p == (unsigned char)c)
      return (void *)p;
  return 0;
}
size_t strlen(const char *s) {
  size_t n = 0;
  while (s[n])
    ++n;
  return n;
}
int strcmp(const char *a, const char *b) {
  while (*a && *a == *b)
    ++a, ++b;
  return (unsigned char)*a - (unsigned char)*b;
}
int strncmp(const char *a, const char *b, size_t n) {
  for (; n; --n, ++a, ++b)
    if (*a != *b || !*a)
      return (unsigned char)*a - (unsigned char)*b;
  return 0;
}
char *strcpy(char *d, const char *s) {
  char *r = d;
  while ((*d++ = *s++))
    ;
  return r;
}
char *strncpy(char *d, const char *s, size_t n) {
  size_t i = 0;
  for (; i < n && s[i]; ++i)
    d[i] = s[i];
  for (; i < n; ++i)
    d[i] = 0;
  return d;
}
char *strcat(char *d, const char *s) {
  strcpy(d + strlen(d), s);
  return d;
}
char *strchr(const char *s, int c) {
  for (;; ++s) {
    if (*s == (char)c)
      return (char *)s;
    if (!*s)
      return 0;
  }
}
char *strrchr(const char *s, int c) {
  const char *r = 0;
  for (;; ++s) {
    if (*s == (char)c)
      r = s;
    if (!*s)
      return (char *)r;
  }
}
char *strstr(const char *h, const char *n) {
  size_t k = strlen(n);
  for (; *h; ++h)
    if (!strncmp(h, n, k))
      return (char *)h;
  return k ? 0 : (char *)h;
}

int abs(int x) { return x < 0 ? -x : x; }
long labs(long x) { return x < 0 ? -x : x; }
long long llabs(long long x) { return x < 0 ? -x : x; }
int isdigit(int c) { return c >= '0' && c <= '9'; }
int isupper(int c) { return c >= 'A' && c <= 'Z'; }
int islower(int c) { return c >= 'a' && c <= 'z'; }
int isalpha(int c) { return isupper(c) || islower(c); }
int isalnum(int c) { return isalpha(c) || isdigit(c); }
int isspace(int c) { return c == ' ' || (c >= '\t' && c <= '\r'); }
int isxdigit(int c) {
  return isdigit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}
int isprint(int c) { return c >= 0x20 && c < 0x7f; }
int toupper(int c) { return islower(c) ? c - 32 : c; }
int tolower(int c) { return isupper(c) ? c + 32 : c; }
unsigned long strtoul(const char *s, char **end, int base) {
  while (isspace(*s))
    ++s;
  int neg = *s == '-';
  if (*s == '-' || *s == '+')
    ++s;
  if ((base == 0 || base == 16) && s[0] == '0' && (s[1] | 32) == 'x')
    s += 2, base = 16;
  else if (base == 0)
    base = *s == '0' ? 8 : 10;
  unsigned long v = 0;
  for (;; ++s) {
    int d = isdigit(*s) ? *s - '0' : isalpha(*s) ? (*s | 32) - 'a' + 10 : 99;
    if (d >= base)
      break;
    v = v * base + d;
  }
  if (end)
    *end = (char *)s;
  return neg ? -v : v;
}
long strtol(const char *s, char **end, int base) {
  return (long)strtoul(s, end, base);
}
int atoi(const char *s) { return (int)strtol(s, 0, 10); }
static unsigned long long rand_state = 1;
int rand(void) {
  rand_state = rand_state * 6364136223846793005ULL + 1;
  return (int)(rand_state >> 33);
}
void srand(unsigned s) { rand_state = s; }
void qsort(void *base, size_t n, size_t size,
           int (*cmp)(const void *, const void *)) {
  unsigned char *b = base;
  for (size_t i = 1; i < n; ++i)
    for (size_t j = i; j > 0 && cmp(b + (j - 1) * size, b + j * size) > 0; --j)
      for (size_t k = 0; k < size; ++k) {
        unsigned char t = b[(j - 1) * size + k];
        b[(j - 1) * size + k] = b[j * size + k];
        b[j * size + k] = t;
      }
}
void *bsearch(const void *key, const void *base, size_t n, size_t size,
              int (*cmp)(const void *, const void *)) {
  const unsigned char *b = base;
  for (size_t i = 0; i < n; ++i)
    if (!cmp(key, b + i * size))
      return (void *)(b + i * size);
  return 0;
}

double fabs(double x) { return __builtin_fabs(x); }
float fabsf(float x) { return __builtin_fabsf(x); }
long double fabsl(long double x) { return __builtin_fabsl(x); }
double copysign(double x, double y) { return __builtin_copysign(x, y); }
float copysignf(float x, float y) { return __builtin_copysignf(x, y); }
long double copysignl(long double x, long double y) {
  return __builtin_copysignl(x, y);
}
double fmax(double x, double y) { return x != x ? y : y != y ? x : x > y ? x : y; }
double fmin(double x, double y) { return x != x ? y : y != y ? x : x < y ? x : y; }

/* Not accurate to the last bit: enough for the tests that classify
 * results. */
static double sqrt_(double x) { /* x finite, >= 0 */
  if (x == 0)
    return x;
  /* Halve the exponent for a first guess, then Newton. */
  union { double d; unsigned long long u; } g = {x};
  g.u = (g.u >> 1) + (1023ULL << 51);
  double r = g.d;
  for (int i = 0; i < 6; ++i)
    r = 0.5 * (r + x / r);
  return r;
}
double cabs(double _Complex z) {
  double a = __builtin_fabs(__real__ z), b = __builtin_fabs(__imag__ z);
  if (a == __builtin_inf() || b == __builtin_inf())
    return __builtin_inf();
  if (a != a || b != b)
    return __builtin_nan("");
  double m = a > b ? a : b;
  if (m == 0)
    return 0;
  a /= m;
  b /= m;
  return m * sqrt_(a * a + b * b);
}
float cabsf(float _Complex z) {
  return (float)cabs((double)__real__ z + 1.0i * (double)__imag__ z);
}
