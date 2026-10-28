void g(void);
int f(int *p, int n)
{
    int a0 = p[0], a1 = p[1], a2 = p[2], a3 = p[3], a4 = p[4], a5 = p[5],
        a6 = p[6], a7 = p[7], a8 = p[8], a9 = p[9], a10 = p[10], a11 = p[11];
    for (int i = 0; i < n; i++) {
        g();
        a0 += a1; a1 ^= a2; a2 += a3; a3 ^= a4; a4 += a5; a5 ^= a6;
        a6 += a7; a7 ^= a8; a8 += a9; a9 ^= a10; a10 += a11; a11 ^= a0;
    }
    return a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7 + a8 + a9 + a10 + a11;
}
