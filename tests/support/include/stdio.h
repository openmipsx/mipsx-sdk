/* Minimal stdio for the SDK's execution tests (tests/README.md); not a libc. */
#ifndef _MINI_STDIO_H
#define _MINI_STDIO_H
#include <stdarg.h>
#include <stddef.h>
typedef struct _mini_FILE FILE;
extern FILE *const stdin, *const stdout, *const stderr;
#define EOF (-1)
int printf(const char *, ...);
int fprintf(FILE *, const char *, ...);
int sprintf(char *, const char *, ...);
int snprintf(char *, size_t, const char *, ...);
int vprintf(const char *, va_list);
int vfprintf(FILE *, const char *, va_list);
int vsprintf(char *, const char *, va_list);
int vsnprintf(char *, size_t, const char *, va_list);
int putchar(int);
int fputc(int, FILE *);
int putc(int, FILE *);
int puts(const char *);
int fputs(const char *, FILE *);
size_t fwrite(const void *, size_t, size_t, FILE *);
int fflush(FILE *);
int getchar(void);
#endif
