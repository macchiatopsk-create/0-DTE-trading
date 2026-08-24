#!/usr/bin/env python3
from math import comb, log2

P = 2**31 - 2**24 + 1
PHI = P - 1
K = 136


def primitive_root(p: int) -> int:
    factors = [2, 127]
    for g in range(2, 1000):
        if all(pow(g, (p - 1)//q, p) != 1 for q in factors):
            return g
    raise RuntimeError('no primitive root found')


def dlog_table(order: int, g: int):
    root = pow(g, PHI//order, P)
    table = {}
    cur = 1
    for e in range(order):
        table[cur] = e
        cur = (cur * root) % P
    assert len(table) == order
    return table


def char_exponent(x: int, order: int, table: dict[int,int]) -> int:
    assert x % P != 0
    return table[pow(x, PHI//order, P)]


def rotate_bits(bits: int, shift: int, mod: int, mask: int) -> int:
    shift %= mod
    if shift == 0:
        return bits
    return ((bits << shift) | (bits >> (mod-shift))) & mask


def theta_norm_factor(u: int) -> int:
    return (pow(u, 6, P) + pow(u, 3, P) + 1) % P


def joint_support_product_norm(items, k: int, mod: int) -> int:
    # DP over Z/256 (product exponent) x Z/mod (norm character exponent).
    mask = (1 << mod) - 1
    dp = [[0]*256 for _ in range(k+1)]
    dp[0][0] = 1
    seen = 0
    for bexp, nexp in items:
        seen += 1
        hi = min(k, seen)
        bexp %= 256
        nexp %= mod
        for j in range(hi, 0, -1):
            prev = dp[j-1]
            cur = dp[j]
            for b, bits in enumerate(prev):
                if bits:
                    tb = (b + bexp) & 255
                    cur[tb] |= rotate_bits(bits, nexp, mod, mask)
    return sum(bits.bit_count() for bits in dp[k])


def main():
    g = primitive_root(P)
    z256 = pow(g,PHI//256,P)
    mu256 = [pow(z256,j,P) for j in range(256)]
    roots = [(j, pow(z256,j,P)) for j in range(1,256)]
    assert len(roots) == 255

    print(f'P={P} g={g} z256={z256}')
    print(f'log2_choose_255_136={log2(comb(255,K)):.12f}')
    print('Ext6 modulus: X^6 + X^3 + 1')
    factors = [(j, theta_norm_factor(u)) for j,u in roots]
    print('distinct_norm_factors=', len({x for _,x in factors}))

    print('\nJOINT PRODUCT-KEY x NORM-CHARACTER SUPPORT')
    for mod in [2,4,8,16,32,64,127]:
        table = dlog_table(mod,g)
        items = [(j, char_exponent(x,mod,table)) for j,x in factors]
        support = joint_support_product_norm(items,K,mod)
        full = 256*mod
        saving = log2(full/support)
        print(f' mod={mod:3d} support={support:6d}/{full:6d} saving={saving:.6f}bits')

if __name__=='__main__':
    main()
