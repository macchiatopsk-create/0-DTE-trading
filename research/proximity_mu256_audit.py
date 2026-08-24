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


def subset_sum_counts(exps, k: int, mod: int):
    dp = [[0]*mod for _ in range(k+1)]
    dp[0][0] = 1
    seen = 0
    for e in exps:
        seen += 1
        hi = min(k, seen)
        e %= mod
        for j in range(hi, 0, -1):
            prev, cur = dp[j-1], dp[j]
            for s, c in enumerate(prev):
                if c:
                    cur[(s+e) % mod] += c
    return dp[k]


def rotate_bits(bits: int, shift: int, mod: int, mask: int) -> int:
    shift %= mod
    if shift == 0:
        return bits
    return ((bits << shift) | (bits >> (mod-shift))) & mask


def subset_sum_support_bitset(exps, k: int, mod: int):
    mask = (1 << mod) - 1
    dp = [0]*(k+1)
    dp[0] = 1
    seen = 0
    for e in exps:
        seen += 1
        hi = min(k, seen)
        for j in range(hi, 0, -1):
            dp[j] |= rotate_bits(dp[j-1], e, mod, mask)
    return dp[k].bit_count()


def theta_norm_factor(u: int) -> int:
    # KoalaBear.Ext6 = F_p[theta]/(theta^6 + theta^3 + 1).
    # Norm(theta-u) = product_i(theta_i-u) = u^6 + u^3 + 1 (degree even).
    return (pow(u, 6, P) + pow(u, 3, P) + 1) % P


def audit_norm(roots, g):
    total = comb(255, K)
    factors = [theta_norm_factor(u) for u in roots]
    assert all(factors)
    print('\nEXT6 THETA NORM')
    print('norm_factor = u^6 + u^3 + 1')
    print('individual_distinct_norm_factors=', len(set(factors)))

    for mod in [2,4,8,16,32,64,127]:
        table = dlog_table(mod,g)
        exps = [char_exponent(x,mod,table) for x in factors]
        counts = subset_sum_counts(exps,K,mod)
        support = sum(c>0 for c in counts)
        avg = total/mod
        print(f' mod={mod:3d} indiv_support={len(set(exps)):3d} subset_support={support:3d}/{mod:3d} '
              f'saving={log2(mod/support):.6f}bits max/avg={max(counts)/avg:.12f} '
              f'min/avg={min(c for c in counts if c)/avg:.12f}')

    mod = 64*127
    table = dlog_table(mod,g)
    exps = [char_exponent(x,mod,table) for x in factors]
    support = subset_sum_support_bitset(exps,K,mod)
    print(f' mod={mod:4d} indiv_support={len(set(exps)):4d} subset_support={support:4d}/{mod:4d} '
          f'saving={log2(mod/support):.6f}bits')


def main():
    g = primitive_root(P)
    z256 = pow(g,PHI//256,P)
    mu256 = [pow(z256,j,P) for j in range(256)]
    roots = [u for u in mu256 if u != 1]
    assert len(roots) == 255

    print(f'P={P} g={g} z256={z256}')
    print(f'log2_choose_255_136={log2(comb(255,K)):.12f}')
    print('Ext6 modulus: X^6 + X^3 + 1')
    audit_norm(roots,g)

if __name__=='__main__':
    main()
