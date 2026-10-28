/* Minimal stdlib for the SDK's execution tests; not a libc. */
#ifndef _MINI_STDLIB_H
#define _MINI_STDLIB_H
#include <stddef.h>
#define EXIT_SUCCESS 0
#define EXIT_FAILURE 1
#define RAND_MAX 0x7fffffff
_Noreturn void abort(void);
_Noreturn void exit(int);
_Noreturn void _exit(int);
void *malloc(size_t);
void *calloc(size_t, size_t);
void *realloc(void *, size_t);
void free(void *);
int abs(int);
long labs(long);
long long llabs(long long);
int atoi(const char *);
long strtol(const char *, char **, int);
unsigned long strtoul(const char *, char **, int);
int rand(void);
void srand(unsigned);
void qsort(void *, size_t, size_t, int (*)(const void *, const void *));
void *bsearch(const void *, const void *, size_t, size_t,
              int (*)(const void *, const void *));
#endif
