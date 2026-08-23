#!/usr/bin/env python3
from math import comb, log2

P = 2**31 - 2**24 + 1
PHI = P - 1
N = 256
K = 136


def primitive_root(p: int) -> int:
    factors = [2, 127]  # p-1 = 2^24 * 127
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
    y = pow(x, PHI//order, P)
    return table[y]


def subset_sum_counts(exps, k: int, mod: int):
    dp = [[0]*mod for _ in range(k+1)]
    dp[0][0] = 1
    seen = 0
    for e in exps:
        seen += 1
        hi = min(k, seen)
        e %= mod
        for j in range(hi, 0, -1):
            prev = dp[j-1]
            cur = dp[j]
            for s, c in enumerate(prev):
                if c:
                    cur[(s+e) % mod] += c
    return dp[k]


def rotate_bits(bits: int, shift: int, mod: int, mask: int) -> int:
    if not bits:
        return 0
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


def summarize_anchor(name: str, a: int, mu256, g, tables):
    if a in mu256:
        return {'name': name, 'status': 'ON_DOMAIN_SKIP'}

    total = comb(255, K)
    result = {'name': name, 'a': a, 'rows': []}

    # Exact count distributions for 64- and 127-primary character quotients.
    for mod in [64, 127]:
        table = tables[mod]
        exps = []
        indiv = [0]*mod
        for u in mu256:
            if u == 1:
                continue
            x = (a-u) % P
            assert x != 0
            e = char_exponent(x, mod, table)
            exps.append(e)
            indiv[e] += 1
        counts = subset_sum_counts(exps, K, mod)
        assert sum(counts) == total
        support = sum(1 for c in counts if c)
        avg = total/mod
        result['rows'].append({
            'mod': mod,
            'individual_support': sum(1 for c in indiv if c),
            'subset_support': support,
            'saving_bits': log2(mod/support),
            'max_over_avg': max(counts)/avg,
            'min_over_avg': min(c for c in counts if c)/avg,
        })

    # Combined quotient character support: 64 * 127 = 8128.
    mod = 64*127
    table = tables[mod]
    exps = []
    indiv = [0]*mod
    for u in mu256:
        if u == 1:
            continue
        x = (a-u) % P
        e = char_exponent(x, mod, table)
        exps.append(e)
        indiv[e] += 1
    support = subset_sum_support_bitset(exps, K, mod)
    result['rows'].append({
        'mod': mod,
        'individual_support': sum(1 for c in indiv if c),
        'subset_support': support,
        'saving_bits': log2(mod/support),
        'max_over_avg': None,
        'min_over_avg': None,
    })
    return result


def main():
    g = primitive_root(P)
    assert PHI == 2**24 * 127
    z256 = pow(g, PHI//256, P)
    mu256 = [pow(z256, j, P) for j in range(256)]
    assert len(set(mu256)) == 256
    assert pow(z256, 256, P) == 1 and pow(z256, 128, P) != 1

    tables = {m: dlog_table(m, g) for m in [64, 127, 64*127]}

    anchors = []
    for order in [512, 1024, 2048, 4096, 8192, 16384]:
        a = pow(g, PHI//order, P)
        anchors.append((f'mu{order}_primitive', a))
    anchors += [('a=2', 2), ('a=-2', P-2), ('a=3', 3), ('a=-3', P-3)]

    print(f'P={P}')
    print(f'primitive_root={g}')
    print(f'z256={z256}')
    print(f'log2_choose_255_136={log2(comb(255,136)):.12f}')
    print()
    for name, a in anchors:
        res = summarize_anchor(name, a, mu256, g, tables)
        print('ANCHOR', name)
        if res.get('status'):
            print(res['status'])
            continue
        print('a=', a)
        for row in res['rows']:
            if row['max_over_avg'] is None:
                print(f" mod={row['mod']:4d} indiv_support={row['individual_support']:4d} subset_support={row['subset_support']:4d} saving={row['saving_bits']:.6f}bits")
            else:
                print(f" mod={row['mod']:4d} indiv_support={row['individual_support']:4d} subset_support={row['subset_support']:4d} saving={row['saving_bits']:.6f}bits max/avg={row['max_over_avg']:.12f} min/avg={row['min_over_avg']:.12f}")
        print()

if __name__ == '__main__':
    main()
