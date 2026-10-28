/* Minimal inttypes.h for the SDK's execution tests; not a libc. */
#ifndef _MINI_INTTYPES_H
#define _MINI_INTTYPES_H
#include <stdint.h>
#define PRId8 __INT8_FMTd__
#define PRIi8 __INT8_FMTi__
#define PRIu8 __UINT8_FMTu__
#define PRIx8 __UINT8_FMTx__
#define PRIX8 __UINT8_FMTX__
#define PRId16 __INT16_FMTd__
#define PRIi16 __INT16_FMTi__
#define PRIu16 __UINT16_FMTu__
#define PRIx16 __UINT16_FMTx__
#define PRIX16 __UINT16_FMTX__
#define PRId32 __INT32_FMTd__
#define PRIi32 __INT32_FMTi__
#define PRIu32 __UINT32_FMTu__
#define PRIx32 __UINT32_FMTx__
#define PRIX32 __UINT32_FMTX__
#define PRId64 __INT64_FMTd__
#define PRIi64 __INT64_FMTi__
#define PRIu64 __UINT64_FMTu__
#define PRIx64 __UINT64_FMTx__
#define PRIX64 __UINT64_FMTX__
#define PRIdPTR __INTPTR_FMTd__
#define PRIuPTR __UINTPTR_FMTu__
#define PRIxPTR __UINTPTR_FMTx__
#define PRIdMAX __INTMAX_FMTd__
#define PRIuMAX __UINTMAX_FMTu__
#define PRIxMAX __UINTMAX_FMTx__
#endif
