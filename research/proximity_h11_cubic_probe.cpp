#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <numeric>
#include <random>
#include <unordered_set>
#include <vector>

using u64 = std::uint64_t;
using u128 = __uint128_t;
static constexpr u64 P = 2130706433ULL;
static constexpr int N = 256;
static constexpr int H = 11;

static inline u64 addm(u64 a, u64 b) { u64 s=a+b; return s>=P ? s-P : s; }
static inline u64 subm(u64 a, u64 b) { return a>=b ? a-b : a+P-b; }
static inline u64 mulm(u64 a, u64 b) { return (u64)((u128)a*b % P); }
static u64 powm(u64 a, u64 e) {
  u64 r=1;
  while(e){ if(e&1) r=mulm(r,a); a=mulm(a,a); e>>=1; }
  return r;
}

struct Graph {
  std::array<u64,N> x{};
  std::array<u64,N> y{};
  std::array<bool,N> inA{};
  std::vector<int> comp;
};

static Graph make_graph(const std::array<u64,N>& x, const std::array<int,H>& A) {
  Graph g; g.x=x; g.inA.fill(false);
  for(int a:A) g.inA[a]=true;
  g.comp.reserve(N-H);
  for(int i=0;i<N;i++) {
    if(g.inA[i]) { g.y[i]=0; continue; }
    u64 v=1;
    for(int a:A) v=mulm(v, subm(x[i],x[a]));
    // x[i]^{-1}=x[-i mod 256]
    v=mulm(v, x[(N-i)&255]);
    g.y[i]=v;
    g.comp.push_back(i);
  }
  return g;
}

static inline u64 invdiff(const std::array<std::array<u64,N>,N>& invd, int a, int b) {
  // 1/(x[a]-x[b])
  return invd[a][b];
}

struct Newton3 { int i0,i1,i2; u64 c0,c1,c2,c3; };

static Newton3 interpolate4(const Graph& g,
    const std::array<std::array<u64,N>,N>& invd,
    int i0,int i1,int i2,int i3) {
  u64 d01=mulm(subm(g.y[i1],g.y[i0]), invdiff(invd,i1,i0));
  u64 d12=mulm(subm(g.y[i2],g.y[i1]), invdiff(invd,i2,i1));
  u64 d23=mulm(subm(g.y[i3],g.y[i2]), invdiff(invd,i3,i2));
  u64 d012=mulm(subm(d12,d01), invdiff(invd,i2,i0));
  u64 d123=mulm(subm(d23,d12), invdiff(invd,i3,i1));
  u64 d0123=mulm(subm(d123,d012), invdiff(invd,i3,i0));
  return {i0,i1,i2,g.y[i0],d01,d012,d0123};
}

static inline u64 eval_newton(const Graph& g,const Newton3& q,int j) {
  // c0 +(x-x0)( c1 +(x-x1)( c2 +(x-x2)c3))
  u64 t=q.c3;
  t=addm(q.c2, mulm(subm(g.x[j],g.x[q.i2]),t));
  t=addm(q.c1, mulm(subm(g.x[j],g.x[q.i1]),t));
  t=addm(q.c0, mulm(subm(g.x[j],g.x[q.i0]),t));
  return t;
}

static std::array<int,H> random_A(std::mt19937_64& rng) {
  std::array<int,N> idx; std::iota(idx.begin(),idx.end(),0);
  for(int i=0;i<H;i++) {
    std::uniform_int_distribution<int> d(i,N-1);
    int j=d(rng); std::swap(idx[i],idx[j]);
  }
  std::array<int,H> A{};
  for(int i=0;i<H;i++) A[i]=idx[i];
  std::sort(A.begin(),A.end());
  return A;
}

static std::array<int,4> random_quad(const std::vector<int>& comp,std::mt19937_64& rng) {
  const int m=(int)comp.size();
  std::array<int,4> q{};
  for(int k=0;k<4;k++) {
    while(true) {
      int v=comp[(size_t)(rng()%m)];
      bool ok=true; for(int t=0;t<k;t++) if(q[t]==v) ok=false;
      if(ok){ q[k]=v; break; }
    }
  }
  return q;
}

int main() {
  const u64 primitive=3;
  const u64 z=powm(primitive,(P-1)/256);
  std::array<u64,N> x{}; x[0]=1;
  for(int i=1;i<N;i++) x[i]=mulm(x[i-1],z);
  if(x[255]==0 || mulm(x[255],z)!=1) return 2;

  static std::array<std::array<u64,N>,N> invd{};
  for(int i=0;i<N;i++) for(int j=0;j<N;j++) if(i!=j)
    invd[i][j]=powm(subm(x[i],x[j]),P-2);

  constexpr int A_TRIALS=64;
  constexpr int QUADS_PER_A=20000;
  const std::uint64_t total_samples=(std::uint64_t)A_TRIALS*QUADS_PER_A;
  std::mt19937_64 rng(20260824ULL ^ 0x11C0B1CULL);

  std::array<std::uint64_t,12> incidence_hist{};
  std::uint64_t rich11=0, ge5=0, ge6=0;
  int global_max=0;

  for(int at=0;at<A_TRIALS;at++) {
    auto A=random_A(rng);
    auto g=make_graph(x,A);
    int local_max=0; std::uint64_t local11=0;
    for(int s=0;s<QUADS_PER_A;s++) {
      auto q=random_quad(g.comp,rng);
      auto cubic=interpolate4(g,invd,q[0],q[1],q[2],q[3]);
      int hits=0;
      for(int j:g.comp) if(eval_newton(g,cubic,j)==g.y[j]) ++hits;
      if(hits>11) { std::cerr << "impossible hits>11\n"; return 3; }
      incidence_hist[hits]++;
      if(hits>=5) ge5++;
      if(hits>=6) ge6++;
      if(hits==11){ rich11++; local11++; }
      local_max=std::max(local_max,hits); global_max=std::max(global_max,hits);
    }
    if(at<8 || local11 || local_max>4) {
      std::cout << "Atrial="<<at<<" local_max="<<local_max<<" rich11_samples="<<local11<<" A=";
      for(int a:A) std::cout<<a<<',';
      std::cout<<"\n";
    }
  }

  std::cout << "P="<<P<<" z256="<<z<<"\n";
  std::cout << "A_trials="<<A_TRIALS<<" quads_per_A="<<QUADS_PER_A
            <<" total_quad_samples="<<total_samples<<"\n";
  std::cout << "incidence histogram:";
  for(int r=4;r<=11;r++) std::cout << " r"<<r<<'='<<incidence_hist[r];
  std::cout << "\n";
  std::cout << "global_max_incidence="<<global_max<<" ge5="<<ge5<<" ge6="<<ge6
            <<" rich11="<<rich11<<"\n";

  // Required shell-11 average partner count from exact ledger after granting h8..10 full packing ceilings.
  const long double required_partners=172726.12312587295L;
  // C(245,4)=? compute exact in 128 then cast.
  u128 c2454=(u128)245*244*243*242/24;
  long double C2454=(long double)c2454;
  long double required_quad_fraction=required_partners*330.0L/C2454;
  std::cout << "C(245,4)="<<(u64)c2454<<" required_quad_fraction_if_h11_closes_residual="
            <<(double)required_quad_fraction<<"\n";
  std::cout << "observed_rich11_fraction="<<(double)((long double)rich11/total_samples)<<"\n";
  if(rich11==0) {
    // Rule-of-three 95% binomial upper estimate, only a research diagnostic, NOT a proof.
    std::cout << "zero-hit rule-of-three 95pct upper~"<<(double)(3.0L/total_samples)
              <<" (diagnostic only, not a theorem)\n";
  }
  return 0;
}
