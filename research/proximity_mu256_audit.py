#!/usr/bin/env python3
from math import comb, log2
import random

P = 2**31 - 2**24 + 1
Q = P**6
BSTAR = Q // 2**128
CAND = comb(255,136)


def primitive_root(p: int) -> int:
    for g in range(2,1000):
        if pow(g,(p-1)//2,p) != 1 and pow(g,(p-1)//127,p) != 1:
            return g
    raise RuntimeError


def exact_key_ledger():
    print('EXACT KEY LEDGER')
    print('P=',P)
    print('Q=P^6=',Q)
    print('B*=floor(Q/2^128)=',BSTAR)
    print('C=choose(255,136)=',CAND)
    print('log2 C=',log2(CAND))
    print('log2 B*=',log2(BSTAR))
    for product_classes in [256,128,64,32,16]:
        key_count = Q * product_classes
        lhs = key_count * BSTAR
        ok = lhs < CAND
        avg = CAND / key_count
        print(f'classes={product_classes:3d}  key*B* < C ? {ok}  '
              f'log2(avg_fiber)={log2(avg):.9f}  '
              f'log2(avg/B*)={log2(avg/BSTAR):+.9f}')


def verify_trade(z256, X, Y):
    # Lift an r-subset of mu64 labels to a union of mu4 cosets in mu256.
    def lift(S):
        return sorted({(r + 64*t) % 256 for r in S for t in range(4)})
    A=lift(X); B=lift(Y)
    assert len(A)==len(B)==4*len(X)
    for k in range(1,7):
        sa=sum(pow(pow(z256,j,P),k,P) for j in A)%P
        sb=sum(pow(pow(z256,j,P),k,P) for j in B)%P
        assert sa==sb, (k,sa,sb)
    ea=sum(A)%256; eb=sum(B)%256
    return A,B,(ea-eb)%256


def search_h4_trade(g,z256, samples=400000):
    # mu4-coset unions automatically kill moments 1,2,3,5,6.
    # Equality of p4 becomes equality of the sum of 8 labels in mu64.
    # Opposite parity of label-sum => product exponent differs by 4 mod 8.
    z64=pow(z256,4,P)
    vals=[pow(z64,r,P) for r in range(64)]
    rng=random.Random(20260824)
    seen={}
    for it in range(samples):
        S=tuple(sorted(rng.sample(range(64),8)))
        s=sum(vals[r] for r in S)%P
        parity=sum(S)&1
        old=seen.get(s)
        if old is None:
            seen[s]=(parity,S)
        elif old[0] != parity:
            T=old[1]
            A,B,diff=verify_trade(z256,S,T)
            print('\nFOUND H4-COSSET TRADE')
            print('iterations=',it+1,'sum=',s)
            print('X=',S,'parity=',parity)
            print('Y=',T,'parity=',old[0])
            print('lift_size_each=',len(A),'product_exponent_diff_mod256=',diff,
                  'diff_mod8=',diff%8,'diff_mod4=',diff%4)
            print('moments p1..p6 verified equal in KoalaBear')
            return True
    print('\nNO H4 trade found in',samples,'samples; distinct sums=',len(seen))
    return False


def main():
    exact_key_ledger()
    g=primitive_root(P)
    z256=pow(g,(P-1)//256,P)
    print('\nprimitive_root=',g,'z256=',z256)
    search_h4_trade(g,z256)

if __name__=='__main__':
    main()
