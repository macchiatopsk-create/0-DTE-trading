#!/usr/bin/env python3
from math import comb, log2, ceil

P = 2**31 - 2**24 + 1
N = 2**18
K = 2**17
TARGET = 139782
Q = P**6
REQ = (Q + 2**128 - 1)//2**128
LP = log2(P)
LREQ = log2(REQ)


def lchoose(n,k):
    if k < 0 or k > n: return float('-inf')
    return log2(comb(n,k))


def top_key_positions(m,l,r,s,a):
    # L(X)=G(X^m) H(X^l).  In Y=X^l, G uses Y^M, H has degree s.
    # Above degree K, top offsets d from the leading monomial can occur at
    # d=i*M+j with i>=0, 0<=j<=s.  d=0 is monic/fixed; every other structurally
    # possible coefficient is pessimistically treated as one K-valued key.
    M=m//l
    sigma=a-K
    maxoff=(sigma-1)//l  # d*l < sigma
    if maxoff <= 0: return 0, []
    offs=set()
    imax=min(r, maxoff//M + 1)
    for i in range(imax+1):
        base=i*M
        if base>maxoff: break
        jmax=min(s,maxoff-base)
        for j in range(jmax+1):
            d=base+j
            if 1 <= d <= maxoff:
                offs.add(d)
    return len(offs), sorted(offs)


def scan():
    rows=[]
    powers=[2**j for j in range(6,18)]  # 64..131072
    for m in powers:
        if N % m: continue
        B=N//m
        if B < 2: continue
        for l in powers:
            if l>m or m%l: continue
            M=m//l
            if M < 2: continue
            # One special large coset is reserved for the partial H block.
            for r in range(B):
                # s in [1,M-1], choose only values that can reach target.
                smin=max(1, ceil((TARGET-r*m)/l))
                if smin >= M: continue
                # Search all possible s; M <= 2048 in this grid, manageable.
                for s in range(smin,M):
                    a=r*m+s*l
                    if a < TARGET or a > N: continue
                    keys,offs=top_key_positions(m,l,r,s,a)
                    fam=lchoose(B-1,r)+lchoose(M,s)
                    slack=fam-keys*LP-LREQ
                    rows.append((slack,a,m,l,r,s,keys,fam,offs[-12:]))
    rows.sort(reverse=True,key=lambda x:x[0])
    return rows


def single_scale():
    rows=[]
    for j in range(6,19):
        m=2**j
        if N%m: continue
        B=N//m
        for r in range(B+1):
            # fixed tail t in one excluded coset if needed
            t=max(0,TARGET-r*m)
            if t>=m: continue
            a=r*m+t
            if a<TARGET or a>N: continue
            avail=B if t==0 else B-1
            if r>avail: continue
            sigma=a-K
            keys=(sigma-1)//m
            fam=lchoose(avail,r)
            slack=fam-keys*LP-LREQ
            rows.append((slack,a,m,r,t,keys,fam))
    rows.sort(reverse=True,key=lambda x:x[0])
    return rows


def main():
    print('p log2=',LP,'required challenge log2=',LREQ,'TARGET=',TARGET)
    print('\nTOP SINGLE-SCALE')
    for row in single_scale()[:15]:
        print('slack=%+.6f a=%d m=%d r=%d tail=%d keys=%d fam_bits=%.6f'%row)
    print('\nTOP TWO-LEVEL HIERARCHICAL')
    rows=scan()
    for slack,a,m,l,r,s,keys,fam,tailoffs in rows[:30]:
        print(f'slack={slack:+.6f} a={a} m={m} l={l} r={r} s={s} keys={keys} fam_bits={fam:.6f} top_offsets_tail={tailoffs}')
    wins=[x for x in rows if x[0]>0]
    print('\npositive-slack families=',len(wins))
    if wins:
        print('BEST WIN=',wins[0])

if __name__=='__main__': main()
