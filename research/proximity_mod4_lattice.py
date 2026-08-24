#!/usr/bin/env python3
from itertools import combinations

P = 2**31 - 2**24 + 1
N = 128


def primitive_root(p: int) -> int:
    for g in range(2,1000):
        if pow(g,(p-1)//2,p) != 1 and pow(g,(p-1)//127,p) != 1:
            return g
    raise RuntimeError


def inv_matrix_mod(A, p):
    n=len(A)
    M=[[(A[i][j]%p) for j in range(n)] + [1 if i==j else 0 for j in range(n)] for i in range(n)]
    for c in range(n):
        piv=next(r for r in range(c,n) if M[r][c]%p)
        M[c],M[piv]=M[piv],M[c]
        inv=pow(M[c][c],p-2,p)
        M[c]=[(x*inv)%p for x in M[c]]
        for r in range(n):
            if r==c: continue
            f=M[r][c]%p
            if f:
                M[r]=[(M[r][j]-f*M[c][j])%p for j in range(2*n)]
    return [row[n:] for row in M]


def matvec(A,v,p):
    return [sum(a*x for a,x in zip(row,v))%p for row in A]


def centered(x,p):
    x%=p
    return x-p if x>p//2 else x


def verify_relation(d,z128):
    assert len(d)==128
    # reduced problem: equal cardinality and first 3 moments on mu128
    assert sum(d)==0
    for k in range(1,4):
        s=sum(di*pow(pow(z128,r,P),k,P) for r,di in enumerate(d))%P
        assert s==0,(k,s)
    # Lift each label r to the mu2 coset {z256^r,z256^(r+128)}.
    weighted=sum(r*di for r,di in enumerate(d))
    return weighted


def main():
    from fpylll import IntegerMatrix, LLL, BKZ

    g=primitive_root(P)
    z128=pow(g,(P-1)//128,P)
    xs=[pow(z128,r,P) for r in range(128)]

    # A*d=0 mod p for rows [1, x, x^2, x^3].
    A=[
        [1]*128,
        xs,
        [x*x%P for x in xs],
        [x*x%P*x%P for x in xs],
    ]
    B=[[A[i][j] for j in range(4)] for i in range(4)]
    Binv=inv_matrix_mod(B,P)

    rows=[]
    # p*e_i for the four pivot variables.
    for i in range(4):
        v=[0]*128; v[i]=P; rows.append(v)
    # One lattice vector for each free coordinate.
    for j in range(4,128):
        c=[A[i][j] for i in range(4)]
        dep=[-sum(Binv[i][t]*c[t] for t in range(4)) % P for i in range(4)]
        v=[0]*128
        for i in range(4): v[i]=centered(dep[i],P)
        v[j]=1
        assert all(x==0 for x in matvec(A,v,P))
        rows.append(v)

    M=IntegerMatrix.from_matrix(rows)
    print('lattice dimension=',M.nrows,'det exponent p^4; running LLL')
    LLL.reduction(M, delta=0.999)

    def inspect(tag):
        best=[]
        for i in range(M.nrows):
            v=[int(M[i,j]) for j in range(M.ncols)]
            norm2=sum(x*x for x in v)
            mx=max(abs(x) for x in v)
            supp=sum(x!=0 for x in v)
            best.append((norm2,mx,supp,i,v))
        best.sort(key=lambda t:t[0])
        print(tag,'best rows:',[(a,b,c,d) for a,b,c,d,_ in best[:10]])
        for norm2,mx,supp,i,v in best[:40]:
            if mx<=1 and any(v):
                w=verify_relation(v,z128)
                print('TERNARY RELATION FOUND row=',i,'norm2=',norm2,'support=',supp,
                      'weighted_mod2=',w%2,'weighted_mod4=',w%4)
                print('positive=',[r for r,x in enumerate(v) if x==1])
                print('negative=',[r for r,x in enumerate(v) if x==-1])
                return v,w
        return None

    hit=inspect('LLL')
    if hit and hit[1]%2==1:
        print('MOD4-CHANGING TRADE FOUND')
        return

    for bs in [10,20,30]:
        print('running BKZ block',bs)
        BKZ.reduction(M, BKZ.Param(block_size=bs, max_loops=3))
        hit=inspect(f'BKZ{bs}')
        if hit and hit[1]%2==1:
            print('MOD4-CHANGING TRADE FOUND')
            return

    print('No odd-weighted ternary basis vector found by this LLL/BKZ search.')

if __name__=='__main__':
    main()
