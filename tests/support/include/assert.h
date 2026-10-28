/* Minimal assert.h for the SDK's execution tests; not a libc. */
#undef assert
#ifdef NDEBUG
#define assert(e) ((void)0)
#else
void __mini_assert(const char *, const char *, int);
#define assert(e) ((e) ? (void)0 : __mini_assert(#e, __FILE__, __LINE__))
#endif
