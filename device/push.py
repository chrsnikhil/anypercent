"""Copy files to the Pi over SFTP.   python device/push.py LOCAL REMOTE [LOCAL REMOTE ...]
From the Pi:                        python device/push.py --get REMOTE LOCAL [REMOTE LOCAL ...]

Connects with anypercent_ssh: the laptop's key, the pinned host key, ANYPERCENT_HOST or the hotspot scan."""
import sys

from anypercent_ssh import connect


def main(argv):
    get = bool(argv) and argv[0] == "--get"
    argv = argv[1:] if get else argv
    if len(argv) < 2 or len(argv) % 2:
        sys.exit(__doc__)
    c, _ = connect(timeout=20)
    s = c.open_sftp()
    for a, b in zip(argv[::2], argv[1::2]):
        if get:
            s.get(a, b)
        else:
            s.put(a, b)
        print("%s -> %s" % (a, b))
    s.close()
    c.close()


if __name__ == "__main__":
    main(sys.argv[1:])
