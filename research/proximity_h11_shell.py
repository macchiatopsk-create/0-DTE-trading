#!/usr/bin/env python3
from math import comb, ceil, log2

P = 2**31 - 2**24 + 1
Q = P**6
FIELD_KEYS = Q * 256
N = comb(256, 128)
REQ = (Q + 2**128 - 1) // 2**128


def ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


def packing_fibre_max(h: int) -> int:
    # Same-key h-subsets cannot share h-7 or more points: cancelling the
    # intersection would give a non-empty trade of size <= 7.
    t = h - 7
    return comb(256, t) // comb(h, t)


def shell_weight(h: int) -> int:
    return comb(256 - 2*h, 128 - h)


def shell_trade_upper(h: int) -> int:
    f = packing_fibre_max(h)
    return comb(256, h) * (f - 1)


def main():
    print('=== 1024-fibre / six-moment + product second-moment ledger ===')
    print('p =', P)
    print('q = p^6 =', Q)
    print('candidate_count C(256,128) =', N)
    print('nominal key count q*256 =', FIELD_KEYS)
    print('average fibre =', N / FIELD_KEYS)
    print('average fibre floor =', N // FIELD_KEYS)
    print('required winning challenges = ceil(q/2^128) =', REQ)
    print('required/average =', REQ / (N / FIELD_KEYS))
    print('deficit bits =', log2(REQ / (N / FIELD_KEYS)))

    target_M = N * REQ
    diagonal = N
    needed_offdiag = target_M - diagonal
    print('\nsecond moment target M >= N*REQ =', target_M)
    print('off-diagonal contribution needed =', needed_offdiag)

    early_max = 0
    print('\npacking ceilings')
    for h in range(8, 13):
        fmax = packing_fibre_max(h)
        tup = shell_trade_upper(h)
        w = shell_weight(h)
        contrib = tup * w
        req_if_alone = ceil_div(needed_offdiag, w)
        ratio = tup / req_if_alone
        print(f'h={h}: fibre_max={fmax}')
        print('  weight=', w)
        print('  trade_upper=', tup)
        print('  trades_required_if_shell_alone=', req_if_alone)
        print('  packing_upper/required=', ratio, 'bits=', log2(ratio) if ratio>0 else float('-inf'))
        if h <= 10:
            early_max += contrib

    residual = max(0, needed_offdiag - early_max)
    w11 = shell_weight(11)
    req11_after_early = ceil_div(residual, w11)
    up11 = shell_trade_upper(11)
    print('\n=== h=11 gate after granting h=8..10 their FULL packing ceilings ===')
    print('early_shell_max_fraction_of_needed=', early_max / needed_offdiag)
    print('residual_second_moment=', residual)
    print('h11_trades_needed_for_residual=', req11_after_early)
    print('h11_packing_trade_upper=', up11)
    print('h11_capacity_ratio=', up11 / req11_after_early)
    print('h11_capacity_bits=', log2(up11 / req11_after_early))

    # A useful normalization: how many same-key partners per 11-set would be
    # needed on average if h=11 alone closed the residual.
    base11 = comb(256, 11)
    print('C(256,11)=', base11)
    print('required average same-key h11 partners=', req11_after_early / base11)
    print('packing max partners per h11 set=', packing_fibre_max(11)-1)

    # Structural locator identity for h=11.
    print('\nlocator identity: equal p1..p6 and equal product =>')
    print('P_A(X)-P_B(X) = X*(a X^3 + b X^2 + c X + d)')
    print('So shell 11 is the first 4-parameter perturbation shell.')

if __name__ == '__main__':
    main()
