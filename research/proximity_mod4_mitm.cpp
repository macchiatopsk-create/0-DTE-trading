#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <vector>

static constexpr uint64_t P = 2130706433ULL;

uint64_t modpow(uint64_t a, uint64_t e){
    uint64_t r=1;
    while(e){ if(e&1) r=(__uint128_t)r*a%P; a=(__uint128_t)a*a%P; e>>=1; }
    return r;
}

uint64_t primitive_root(){
    for(uint64_t g=2;g<1000;g++){
        if(modpow(g,(P-1)/2)!=1 && modpow(g,(P-1)/127)!=1) return g;
    }
    return 0;
}

struct Rec{
    uint32_t s1,s2,s3;
    uint8_t parity;
    uint8_t pad[3]{};
    bool operator<(Rec const& o) const{
        if(s1!=o.s1) return s1<o.s1;
        if(s2!=o.s2) return s2<o.s2;
        if(s3!=o.s3) return s3<o.s3;
        return parity<o.parity;
    }
};

int main(){
    uint64_t g=primitive_root();
    uint64_t z=modpow(g,(P-1)/128);
    std::array<uint64_t,128> x{},x2{},x3{};
    x[0]=1;
    for(int i=1;i<128;i++) x[i]=(__uint128_t)x[i-1]*z%P;
    for(int i=0;i<128;i++){ x2[i]=(__uint128_t)x[i]*x[i]%P; x3[i]=(__uint128_t)x2[i]*x[i]%P; }

    size_t n = 128ULL*127*126*125/24;
    std::vector<Rec> v; v.reserve(n);
    for(int a=0;a<125;a++) for(int b=a+1;b<126;b++) for(int c=b+1;c<127;c++) for(int d=c+1;d<128;d++){
        uint64_t s1=(x[a]+x[b]+x[c]+x[d])%P;
        uint64_t s2=(x2[a]+x2[b]+x2[c]+x2[d])%P;
        uint64_t s3=(x3[a]+x3[b]+x3[c]+x3[d])%P;
        v.push_back({(uint32_t)s1,(uint32_t)s2,(uint32_t)s3,(uint8_t)((a+b+c+d)&1),{0,0,0}});
    }
    std::cout << "records="<<v.size()<<" expected="<<n<<" sizeof="<<sizeof(Rec)<<"\n";
    std::sort(v.begin(),v.end());
    uint64_t groups=0, collision_groups=0, mixed_parity_groups=0, max_group=0;
    for(size_t i=0;i<v.size();){
        size_t j=i+1;
        while(j<v.size() && v[j].s1==v[i].s1 && v[j].s2==v[i].s2 && v[j].s3==v[i].s3) j++;
        groups++;
        uint64_t sz=j-i; if(sz>max_group) max_group=sz;
        if(sz>1){
            collision_groups++;
            bool p0=false,p1=false;
            for(size_t k=i;k<j;k++){ if(v[k].parity) p1=true; else p0=true; }
            if(p0&&p1) mixed_parity_groups++;
        }
        i=j;
    }
    std::cout << "groups="<<groups<<" collision_groups="<<collision_groups
              <<" mixed_parity_groups="<<mixed_parity_groups<<" max_group="<<max_group<<"\n";
    if(mixed_parity_groups){
        std::cout << "MOD4 COUNTEREXAMPLE EXISTS at support <=8\n";
        return 2;
    }
    std::cout << "NO mixed-parity 4-subset moment collision; mod4 survives support<=8 exact scan\n";
    return 0;
}
