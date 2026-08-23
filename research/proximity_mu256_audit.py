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


def subset_pair_counts(exp_pairs, k: int, mod: int):
    nstate = mod*mod
    dp = [[0]*nstate for _ in range(k+1)]
    dp[0][0] = 1
    seen = 0
    for e1,e2 in exp_pairs:
        seen += 1
        hi = min(k, seen)
        e1 %= mod; e2 %= mod
        for j in range(hi, 0, -1):
            prev, cur = dp[j-1], dp[j]
            for idx, c in enumerate(prev):
                if not c:
                    continue
                s1, s2 = divmod(idx, mod)
                ni = ((s1+e1)%mod)*mod + ((s2+e2)%mod)
                cur[ni] += c
    return dp[k]


def summarize_single(name, a, roots, tables):
    total = comb(255,K)
    out=[]
    for mod in [64,127]:
        table=tables[mod]
        exps=[char_exponent((a-u)%P,mod,table) for u in roots]
        counts=subset_sum_counts(exps,K,mod)
        support=sum(c>0 for c in counts)
        avg=total/mod
        out.append((mod,support,log2(mod/support),max(counts)/avg,min(c for c in counts if c)/avg))
    return out


def summarize_joint(name, a, b, roots, tables):
    total=comb(255,K)
    rows=[]
    for mod in [4,8,16,32]:
        table=tables[mod]
        pairs=[]
        for u in roots:
            x=(a-u)%P; y=(b-u)%P
            assert x and y
            pairs.append((char_exponent(x,mod,table),char_exponent(y,mod,table)))
        counts=subset_pair_counts(pairs,K,mod)
        support=sum(c>0 for c in counts)
        avg=total/(mod*mod)
        rows.append({
            'mod':mod,
            'support':support,
            'full':mod*mod,
            'saving_bits':log2((mod*mod)/support),
            'max_over_avg':max(counts)/avg,
            'min_over_avg':min(c for c in counts if c)/avg,
        })
    return rows


def main():
    g=primitive_root(P)
    z256=pow(g,PHI//256,P)
    mu256=[pow(z256,j,P) for j in range(256)]
    roots=[u for u in mu256 if u != 1]
    assert len(roots)==255
    tables={m:dlog_table(m,g) for m in [4,8,16,32,64,127]}

    a512=pow(g,PHI//512,P)
    a1024=pow(g,PHI//1024,P)
    candidates={
        'a512':a512,
        '-a512':(-a512)%P,
        'a512_inv':pow(a512,P-2,P),
        'a512*z256':a512*z256%P,
        'a1024':a1024,
        'a1024_inv':pow(a1024,P-2,P),
        '2':2,
        '-2':P-2,
        '3':3,
    }

    print(f'P={P} g={g} z256={z256}')
    print(f'log2_choose={log2(comb(255,K)):.12f}')
    print('SINGLE sanity')
    for name in ['a512','a1024','2']:
        print(name, summarize_single(name,candidates[name],roots,tables))

    pair_names=[
        ('a512','-a512'),
        ('a512','a512_inv'),
        ('a512','a512*z256'),
        ('a1024','a1024_inv'),
        ('2','-2'),
        ('2','3'),
    ]
    print('\nJOINT')
    for x,y in pair_names:
        print('PAIR',x,y)
        for r in summarize_joint(f'{x},{y}',candidates[x],candidates[y],roots,tables):
            print(' mod={mod:2d} support={support:4d}/{full:4d} saving={saving_bits:.6f}bits max/avg={max_over_avg:.12f} min/avg={min_over_avg:.12f}'.format(**r))

if __name__=='__main__':
    main()
