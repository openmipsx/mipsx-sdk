/* Minimal complex.h for the SDK's execution tests; not a libm. */
#ifndef _MINI_COMPLEX_H
#define _MINI_COMPLEX_H
#define complex _Complex
#define _Complex_I (__extension__ 1.0iF)
#define I _Complex_I
#define creal(z) __real__(z)
#define cimag(z) __imag__(z)
#define crealf(z) __real__(z)
#define cimagf(z) __imag__(z)
#define creall(z) __real__(z)
#define cimagl(z) __imag__(z)
#define CMPLX(x, y) __builtin_complex((double)(x), (double)(y))
#define CMPLXF(x, y) __builtin_complex((float)(x), (float)(y))
double cabs(double _Complex);
float cabsf(float _Complex);
#endif
