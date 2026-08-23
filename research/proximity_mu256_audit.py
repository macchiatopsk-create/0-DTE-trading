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


def dlog_small(x: int, root: int, order: int, p: int) -> int:
    cur = 1
    for e in range(order):
        if cur == x:
            return e
        cur = (cur * root) % p
    raise RuntimeError(f'dlog failed for order {order}')


def char_exp64(x: int, g: int) -> int:
    # x^((p-1)/64) is a 64th root of unity; return its exponent vs g^((p-1)/64)
    r64 = pow(g, PHI//64, P)
    y = pow(x, PHI//64, P)
    return dlog_small(y, r64, 64, P)


def subset_sum_counts(exps, k: int, mod: int = 64):
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


def aggregate(counts64, mod):
    out = [0]*mod
    for e,c in enumerate(counts64):
        out[e % mod] += c
    return out


def summarize_anchor(name: str, a: int, mu256, g):
    if a in mu256:
        return {'name': name, 'status': 'ON_DOMAIN_SKIP'}
    exps = []
    indiv = [0]*64
    for u in mu256:
        if u == 1:
            continue
        x = (a-u) % P
        assert x != 0
        e = char_exp64(x, g)
        exps.append(e)
        indiv[e] += 1
    counts64 = subset_sum_counts(exps, K, 64)
    total = comb(255, K)
    assert sum(counts64) == total
    rows = []
    for mod in [2,4,8,16,32,64]:
        cc = aggregate(counts64, mod)
        support = sum(1 for c in cc if c)
        mx = max(cc)
        mn = min(c for c in cc if c)
        avg = total / mod
        rows.append({
            'mod': mod,
            'support': support,
            'saving_bits_if_support_only': log2(mod/support),
            'max_over_avg': mx/avg,
            'min_over_avg': mn/avg,
        })
    return {
        'name': name,
        'a': a,
        'individual_nonzero_classes_mod64': sum(1 for c in indiv if c),
        'individual_class_counts_mod64': indiv,
        'subset_product_rows': rows,
    }


def main():
    g = primitive_root(P)
    assert PHI == 2**24 * 127
    z256 = pow(g, PHI//256, P)
    mu256 = [pow(z256, j, P) for j in range(256)]
    assert len(set(mu256)) == 256
    assert pow(z256, 256, P) == 1 and pow(z256, 128, P) != 1

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
        res = summarize_anchor(name, a, mu256, g)
        print('ANCHOR', name)
        if res.get('status'):
            print(res['status'])
            continue
        print('a=', a)
        print('individual_nonzero_classes_mod64=', res['individual_nonzero_classes_mod64'])
        for row in res['subset_product_rows']:
            print(' mod={mod:2d} support={support:2d} saving={saving_bits_if_support_only:.6f}bits max/avg={max_over_avg:.12f} min/avg={min_over_avg:.12f}'.format(**row))
        print()

if __name__ == '__main__':
    main()
