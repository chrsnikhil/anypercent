import ctypes
import os
import subprocess

import pytest

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U8, U16, U32, I16, I32 = ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int16, ctypes.c_int32


def make(target):
    r = subprocess.run(["make", target], cwd=KIT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return os.path.join(KIT, target)


@pytest.fixture(scope="session")
def kit():
    so = ctypes.CDLL(make("out/libarcade.so"))
    so.ac_fmul.restype = I32; so.ac_fmul.argtypes = [I32, I32]
    so.ac_fdiv.restype = I32; so.ac_fdiv.argtypes = [I32, I32]
    so.ac_sin.restype = I16; so.ac_sin.argtypes = [U16]
    so.ac_cos.restype = I16; so.ac_cos.argtypes = [U16]
    so.ac_atan2.restype = U16; so.ac_atan2.argtypes = [I32, I32]
    so.ac_isqrt.restype = U32; so.ac_isqrt.argtypes = [U32]
    so.ac_rng16.restype = U16; so.ac_rng16.argtypes = [U16]
    so.ac_rng32.restype = U32; so.ac_rng32.argtypes = [U32]
    so.ac_seed_mix.restype = U32; so.ac_seed_mix.argtypes = [U32, U32]
    return so
