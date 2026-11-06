"""Save what the DSI panel is showing (the framebuffer on the active CRTC) as a PNG.   sudo python3 drmgrab.py OUT.png

Under KMS the program on screen (the launcher's SDL window, RetroArch) scans out its own buffer, which /dev/fb0 does
not show; this reads that buffer through the DRM ioctls (GETFB needs root). Works for the linear XRGB8888 / RGB565
buffers vc4 scans out. Needs python3-pil."""
import ctypes
import fcntl
import mmap
import os
import struct
import sys

from PIL import Image


def iowr(nr, size):
    return (3 << 30) | (size << 16) | (ord("d") << 8) | nr


GETRESOURCES, GETCRTC, GETFB, MAP_DUMB = iowr(0xA0, 64), iowr(0xA1, 104), iowr(0xAD, 28), iowr(0xB3, 16)


VC4_T_TILED = 0x0700000000000001        # DRM_FORMAT_MOD_BROADCOM_VC4_T_TILED: what Mesa's vc4 GL scans out


def modifier(fd, fb_id):
    """The framebuffer's format modifier (GETFB2), 0 = linear."""
    b = bytearray(104)
    struct.pack_into("<I", b, 0, fb_id)
    try:
        fcntl.ioctl(fd, iowr(0xCE, 104), b)
    except OSError:
        return 0
    return struct.unpack_from("<Q", b, 72)[0] if struct.unpack_from("<I", b, 16)[0] & 2 else 0


def detile_t32(src, w, h):
    """VC4 T format, 32 bpp -> linear rows. 4 KB tiles of 32 x 32 px in boustrophedon order, each 2 x 2 subtiles of
    1 KB (order depends on the tile row's parity), each 4 x 4 utiles of 4 x 4 px (64 bytes, row-major)."""
    tiles_w = (w + 31) // 32
    even, odd = (0, 3, 1, 2), (2, 1, 3, 0)
    out = bytearray(w * h * 4)
    for uy in range(h // 4):
        ty, odd_row = uy >> 3, (uy >> 3) & 1
        for ux in range(w // 4):
            tx = ux >> 3
            tile = (ty * tiles_w + (tiles_w - 1 - tx if odd_row else tx)) * 4096
            s = ((uy >> 2) & 1) << 1 | ((ux >> 2) & 1)
            base = tile + 1024 * (odd if odd_row else even)[s] + 64 * ((uy & 3) * 4 + (ux & 3))
            for r in range(4):
                d = ((uy * 4 + r) * w + ux * 4) * 4
                out[d:d + 16] = src[base + r * 16:base + r * 16 + 16]
    return bytes(out)


def main(out):
    fd = os.open("/dev/dri/card0", os.O_RDWR)
    res = bytearray(64)
    fcntl.ioctl(fd, GETRESOURCES, res)
    n_crtcs = struct.unpack_from("<I", res, 36)[0]
    buf = ctypes.create_string_buffer(4 * n_crtcs)
    res = bytearray(64)
    struct.pack_into("<Q", res, 8, ctypes.addressof(buf))
    struct.pack_into("<I", res, 36, n_crtcs)
    fcntl.ioctl(fd, GETRESOURCES, res)
    crtc_ids = struct.unpack("<%dI" % n_crtcs, buf.raw)
    for cid in crtc_ids:
        c = bytearray(104)
        struct.pack_into("<I", c, 12, cid)
        fcntl.ioctl(fd, GETCRTC, c)
        fb_id = struct.unpack_from("<I", c, 16)[0]
        if not fb_id:
            continue
        fb = bytearray(28)
        struct.pack_into("<I", fb, 0, fb_id)
        fcntl.ioctl(fd, GETFB, fb)
        _, w, h, pitch, bpp, depth, handle = struct.unpack("<7I", fb)
        m = bytearray(16)
        struct.pack_into("<I", m, 0, handle)
        fcntl.ioctl(fd, MAP_DUMB, m)
        off = struct.unpack_from("<Q", m, 8)[0]
        mod = modifier(fd, fb_id)
        size = pitch * h if mod != VC4_T_TILED else 4096 * ((w + 31) // 32) * ((h + 31) // 32)
        data = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ, offset=off)[:]
        if mod == VC4_T_TILED:
            if bpp != 32:
                sys.exit("T-tiled %d bpp not handled" % bpp)
            data, pitch = detile_t32(data, w, h), w * 4
        if bpp == 32:
            img = Image.frombuffer("RGBX", (w, h), data, "raw", "BGRX", pitch, 1).convert("RGB")
        elif bpp == 16:
            img = Image.frombuffer("RGB", (w, h), data, "raw", "BGR;16", pitch, 1)
        else:
            sys.exit("unsupported bpp %d" % bpp)
        img.save(out)
        print("crtc %d fb %d %dx%d bpp %d depth %d -> %s" % (cid, fb_id, w, h, bpp, depth, out))
        return
    sys.exit("no active CRTC")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screen.png")
