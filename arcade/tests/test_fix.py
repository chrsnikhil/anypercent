import math


def test_fmul_and_fdiv(kit):
    one = 65536
    assert kit.ac_fmul(3 * one, one // 2) == 3 * one // 2
    assert kit.ac_fmul(-2 * one, 3 * one) == -6 * one
    assert kit.ac_fdiv(one, 4 * one) == one // 4
    assert kit.ac_fdiv(-3 * one, 2 * one) == -3 * one // 2
    assert kit.ac_fdiv(30000 * one, one // 65536) == 2**31 - 1      # saturates


def test_sin_cos_table(kit):
    for a in range(0, 1024, 7):
        want = math.sin(2 * math.pi * a / 1024) * 16384
        assert abs(kit.ac_sin(a) - want) <= 1
        assert abs(kit.ac_cos(a) - math.cos(2 * math.pi * a / 1024) * 16384) <= 1
    assert kit.ac_sin(256) == 16384 and kit.ac_cos(0) == 16384 and kit.ac_sin(1024 + 5) == kit.ac_sin(5)


def test_atan2_quadrants(kit):
    assert kit.ac_atan2(0, 100) == 0
    assert kit.ac_atan2(100, 0) == 256
    assert kit.ac_atan2(0, -100) == 512
    assert kit.ac_atan2(-100, 0) == 768
    for a in range(0, 1024, 13):
        y = round(math.sin(2 * math.pi * a / 1024) * 10000)
        x = round(math.cos(2 * math.pi * a / 1024) * 10000)
        d = (kit.ac_atan2(y, x) - a) % 1024
        assert min(d, 1024 - d) <= 2


def test_isqrt(kit):
    for v in (0, 1, 2, 3, 4, 15, 16, 17, 99, 100, 65535, 65536, 2**31, 2**32 - 1):
        assert kit.ac_isqrt(v) == math.isqrt(v)


def test_fdiv_by_zero_saturates_by_the_sign(kit):
    assert kit.ac_fdiv(5, 0) == 2**31 - 1
    assert kit.ac_fdiv(-5, 0) == -2**31
    assert kit.ac_fdiv(0, 0) == 0
    assert kit.ac_fdiv(-2**31, -1) == 2**31 - 1                     # the one quotient that overflows saturates too
