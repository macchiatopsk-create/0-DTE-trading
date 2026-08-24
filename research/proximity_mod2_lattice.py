#!/usr/bin/env python3
import random

P = 2**31 - 2**24 + 1
N = 256
ROWS = 7  # cardinality + moments 1..6


def primitive_root(p: int) -> int:
    for g in range(2,1000):
        if pow(g,(p-1)//2,p)!=1 and pow(g,(p-1)//127,p)!=1:
            return g
    raise RuntimeError


def inv_matrix_mod(A,p):
    n=len(A)
    M=[[(A[i][j]%p) for j in range(n)]+[1 if i==j else 0 for j in range(n)] for i in range(n)]
    for c in range(n):
        piv=next(r for r in range(c,n) if M[r][c]%p)
        M[c],M[piv]=M[piv],M[c]
        z=pow(M[c][c],p-2,p)
        M[c]=[(x*z)%p for x in M[c]]
        for r in range(n):
            if r==c: continue
            f=M[r][c]%p
            if f: M[r]=[(M[r][j]-f*M[c][j])%p for j in range(2*n)]
    return [r[n:] for r in M]


def centered(x,p):
    x%=p
    return x-p if x>p//2 else x


def matvec(A,v,p):
    return [sum(a*x for a,x in zip(row,v))%p for row in A]


def recenter_mu8(v):
    # coset j + 32*t, t=0..7. Complete mu8 cosets kill moments 1..6.
    intervals=[]
    for j in range(32):
        vals=[v[j+32*t] for t in range(8)]
        lo=max(-1-x for x in vals); hi=min(1-x for x in vals)
        if lo>hi: return None
        intervals.append((lo,hi))
    sv=sum(v)
    if sv%8: return None
    target=-sv//8
    L=sum(a for a,b in intervals); H=sum(b for a,b in intervals)
    if not (L<=target<=H): return None
    cs=[a for a,b in intervals]; rem=target-L
    for j,(lo,hi) in enumerate(intervals):
        q=min(rem,hi-lo); cs[j]+=q; rem-=q
    if rem: return None
    w=v[:]
    for j,c in enumerate(cs):
        for t in range(8): w[j+32*t]+=c
    if sum(w)!=0 or max(abs(x) for x in w)>1: return None
    return w


def verify(w,z):
    assert sum(w)==0 and max(abs(x) for x in w)<=1
    for k in range(1,7):
        s=sum(di*pow(pow(z,r,P),k,P) for r,di in enumerate(w))%P
        assert s==0,(k,s)
    return sum(r*di for r,di in enumerate(w))


def main():
    from fpylll import IntegerMatrix, LLL, BKZ
    g=primitive_root(P); z=pow(g,(P-1)//256,P)
    xs=[pow(z,r,P) for r in range(256)]
    A=[[1]*256]
    for k in range(1,7): A.append([pow(x,k,P) for x in xs])
    B=[[A[i][j] for j in range(ROWS)] for i in range(ROWS)]
    Binv=inv_matrix_mod(B,P)

    rows=[]
    for i in range(ROWS):
        v=[0]*256; v[i]=P; rows.append(v)
    for j in range(ROWS,256):
        c=[A[i][j] for i in range(ROWS)]
        dep=[-sum(Binv[i][t]*c[t] for t in range(ROWS))%P for i in range(ROWS)]
        v=[0]*256
        for i in range(ROWS): v[i]=centered(dep[i],P)
        v[j]=1
        assert all(x==0 for x in matvec(A,v,P))
        rows.append(v)

    M=IntegerMatrix.from_matrix(rows)
    print('dimension=256 det=p^7; LLL')
    LLL.reduction(M,delta=0.999)
    for bs in [10,20,30]:
        print('BKZ',bs)
        BKZ.reduction(M,BKZ.Param(block_size=bs,max_loops=3))

    basis=[]
    for i in range(256):
        v=[int(M[i,j]) for j in range(256)]
        basis.append(v)
    basis.sort(key=lambda v:sum(x*x for x in v))
    print('best=',[(sum(x*x for x in v),max(abs(x) for x in v),sum(x!=0 for x in v)) for v in basis[:20]])

    checked=0; rec=0
    def test(v,tag):
        nonlocal checked,rec
        checked+=1
        w=recenter_mu8(v)
        if w is None: return False
        rec+=1
        wt=verify(w,z)
        if wt&1:
            # Rotate by t if necessary to avoid exponent 0 in support. Rotation
            # preserves all moment equalities and weighted parity because sum d=0.
            supp={i for i,x in enumerate(w) if x}
            shift=next(t for t in range(256) if (-t)%256 not in supp)
            wr=[0]*256
            for i,x in enumerate(w): wr[(i+shift)%256]=x
            wt2=verify(wr,z)
            assert wt2&1
            print('PRODUCT-PARITY COUNTEREXAMPLE',tag,'support=',len(supp),'shift=',shift,'weight_mod2=',wt2&1,'mod8=',wt2%8)
            print('positive=',[i for i,x in enumerate(wr) if x==1])
            print('negative=',[i for i,x in enumerate(wr) if x==-1])
            return True
        return False

    for i,v in enumerate(basis):
        if test(v,f'basis[{i}]') or test([-x for x in v],f'-basis[{i}]'): return

    rng=random.Random(20260824); pool=basis[:64]
    for it in range(100000):
        m=rng.choice([2,2,3,3,4])
        ids=rng.sample(range(len(pool)),m); cs=[rng.choice([-1,1]) for _ in ids]
        v=[0]*256
        for idx,c in zip(ids,cs):
            b=pool[idx]
            for j in range(256): v[j]+=c*b[j]
        if test(v,f'random[{it}] ids={ids} cs={cs}'): return
    print('No product-parity ternary trade found; checked=',checked,'recentered=',rec)

if __name__=='__main__': main()
