"""Any% Remote: use the laptop keyboard as the handheld's keyboard over Wi-Fi.
Run on the laptop (python remote_keys.py [host]); keep the small window focused while playing.
Keys: arrows, X = A, Z = B, A/S = L/R, Enter = Start, Backspace = Select, Esc = back to launcher, F1 = RetroArch menu."""
import sys
import threading
import pygame

from anypercent_ssh import connect

HOST = sys.argv[1] if len(sys.argv) > 1 else None             # default: found on the hotspot (anypercent_ssh)
MAP = {pygame.K_ESCAPE: 1, pygame.K_BACKSPACE: 14, pygame.K_RETURN: 28, pygame.K_a: 30, pygame.K_s: 31,
       pygame.K_z: 44, pygame.K_x: 45, pygame.K_F1: 59, pygame.K_UP: 103, pygame.K_LEFT: 105,
       pygame.K_RIGHT: 106, pygame.K_DOWN: 108}


def main():
    pygame.init()
    screen = pygame.display.set_mode((460, 260))
    pygame.display.set_caption("Any% Remote")
    font = pygame.font.SysFont("consolas", 18)

    def draw(lines, colour=(230, 230, 230)):
        screen.fill((20, 22, 30))
        for i, t in enumerate(lines):
            screen.blit(font.render(t, True, colour), (16, 16 + i * 26))
        pygame.display.flip()

    draw(["Connecting to " + (HOST or "the handheld") + " ..."])
    c, _ = connect(HOST, timeout=10)
    chan = c.get_transport().open_session()
    import socket
    c.get_transport().sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # send each key at once
    chan.exec_command("sudo python3 /opt/anypercent/tools/vkbd_stream.py")
    state = {"ready": False}

    def reader():
        buf = b""
        while True:
            data = chan.recv(256)
            if not data:
                break
            buf += data
            if b"ready" in buf:
                state["ready"] = True
    threading.Thread(target=reader, daemon=True).start()

    help_lines = ["Any% Remote - keep this window focused", "",
                  "Arrows move    X = A    Z = B", "A / S = L / R   Enter = Start",
                  "Backspace = Select   Esc = back to launcher", "F1 = RetroArch menu", "",
                  "Close this window to stop."]
    running, clock = True, pygame.time.Clock()
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type in (pygame.KEYDOWN, pygame.KEYUP) and ev.key in MAP:
                chan.sendall(("d %d\n" if ev.type == pygame.KEYDOWN else "u %d\n") % MAP[ev.key])
            elif ev.type == pygame.WINDOWFOCUSLOST:
                for code in MAP.values():            # release everything when the window loses focus
                    chan.sendall(("u %d\n" % code))
        draw(help_lines if state["ready"] else ["Connected, starting the virtual keyboard ..."],
             (150, 230, 90) if state["ready"] else (230, 230, 230))
        clock.tick(120)
    try:
        chan.sendall("q\n")
    except Exception:
        pass
    c.close()
    pygame.quit()


if __name__ == "__main__":
    main()
