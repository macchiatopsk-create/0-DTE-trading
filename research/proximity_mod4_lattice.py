#!/usr/bin/env python3
import random

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
    assert sum(d)==0
    assert max(abs(x) for x in d)<=1
    for k in range(1,4):
        s=sum(di*pow(pow(z128,r,P),k,P) for r,di in enumerate(d))%P
        assert s==0,(k,s)
    return sum(r*di for r,di in enumerate(d))


def recenter_mu4(v):
    """Add integer multiples of complete mu4 cosets j+32*t.

    Such shifts preserve x,x^2,x^3 moments exactly.  Choose shifts so every
    coordinate lands in {-1,0,1} and total cardinality remains zero.
    """
    intervals=[]
    for j in range(32):
        vals=[v[j+32*t] for t in range(4)]
        lo=max(-1-x for x in vals)
        hi=min( 1-x for x in vals)
        if lo>hi:
            return None
        intervals.append([lo,hi])
    sv=sum(v)
    if sv % 4:
        return None
    target=-sv//4
    lo_sum=sum(a for a,b in intervals)
    hi_sum=sum(b for a,b in intervals)
    if not (lo_sum<=target<=hi_sum):
        return None
    cs=[a for a,b in intervals]
    rem=target-lo_sum
    for j,(lo,hi) in enumerate(intervals):
        add=min(rem,hi-lo)
        cs[j]+=add
        rem-=add
    assert rem==0 and sum(cs)==target
    w=v[:]
    for j,c in enumerate(cs):
        for t in range(4):
            w[j+32*t]+=c
    assert sum(w)==0 and max(abs(x) for x in w)<=1
    return w


def main():
    from fpylll import IntegerMatrix, LLL, BKZ

    g=primitive_root(P)
    z128=pow(g,(P-1)//128,P)
    xs=[pow(z128,r,P) for r in range(128)]
    A=[
        [1]*128,
        xs,
        [x*x%P for x in xs],
        [x*x%P*x%P for x in xs],
    ]
    B=[[A[i][j] for j in range(4)] for i in range(4)]
    Binv=inv_matrix_mod(B,P)

    rows=[]
    for i in range(4):
        v=[0]*128; v[i]=P; rows.append(v)
    for j in range(4,128):
        c=[A[i][j] for i in range(4)]
        dep=[-sum(Binv[i][t]*c[t] for t in range(4)) % P for i in range(4)]
        v=[0]*128
        for i in range(4): v[i]=centered(dep[i],P)
        v[j]=1
        assert all(x==0 for x in matvec(A,v,P))
        rows.append(v)

    M=IntegerMatrix.from_matrix(rows)
    print('lattice dimension=',M.nrows,'det exponent p^4')
    LLL.reduction(M, delta=0.999)
    for bs in [10,20,30,40]:
        print('running BKZ block',bs)
        BKZ.reduction(M, BKZ.Param(block_size=bs, max_loops=4))

    basis=[]
    for i in range(M.nrows):
        v=[int(M[i,j]) for j in range(M.ncols)]
        basis.append(v)
    basis.sort(key=lambda v:sum(x*x for x in v))
    print('best raw basis:',[(sum(x*x for x in v),max(abs(x) for x in v),sum(x!=0 for x in v)) for v in basis[:20]])

    checked=0; recentered=0; odd=0
    def test(v,tag):
        nonlocal checked,recentered,odd
        checked+=1
        # Ignore huge representatives: recenter intervals cannot rescue a coset range >2.
        w=recenter_mu4(v)
        if w is None:
            return False
        recentered+=1
        weight=verify_relation(w,z128)
        parity=weight&1
        if parity:
            odd+=1
            print('MOD4-CHANGING TERNARY TRADE FOUND',tag)
            print('support=',sum(x!=0 for x in w),'weight_mod2=',parity,'weight_mod4=',weight%4)
            print('positive=',[i for i,x in enumerate(w) if x==1])
            print('negative=',[i for i,x in enumerate(w) if x==-1])
            return True
        return False

    for i,v in enumerate(basis):
        if test(v,f'basis[{i}]'):
            return
        if test([-x for x in v],f'-basis[{i}]'):
            return

    # Random short combinations of the best BKZ vectors.  Coset recentering can
    # turn max-coeff 2/3 representatives into ternary relations, so search the
    # quotient around the structured shortest shell rather than basis rows only.
    rng=random.Random(20260824)
    pool=basis[:48]
    for it in range(200000):
        terms=rng.sample(range(len(pool)), rng.choice([2,2,2,3,3,4]))
        coeffs=[rng.choice([-1,1]) for _ in terms]
        v=[0]*128
        for idx,c in zip(terms,coeffs):
            b=pool[idx]
            for j in range(128): v[j]+=c*b[j]
        if test(v,f'random[{it}] terms={terms} coeffs={coeffs}'):
            return
    print('No odd ternary trade after coset recenter search.')
    print('checked=',checked,'recentered=',recentered,'odd=',odd)

if __name__=='__main__':
    main()
