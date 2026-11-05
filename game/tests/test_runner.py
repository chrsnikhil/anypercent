import os
import subprocess

from conftest import OUT_DIR, START, TEMPLATE_ROM


def run(runner, lines, *extra):
    path = os.path.join(OUT_DIR, "runner_script.txt")
    with open(path, "w") as f:
        f.write("".join("%x %d\n" % kv for kv in lines))
    r = subprocess.run([runner, TEMPLATE_ROM, path, *extra], capture_output=True, text=True, check=True)
    return [line.split() for line in r.stdout.splitlines()]


def test_one_line_per_frame(runner):
    rows = run(runner, [(0, 30), (START, 5)])
    assert [int(r[0]) for r in rows] == list(range(1, 36))


def test_same_script_same_memory(runner):
    script = [(0, 40), (START, 3), (0, 20)]
    assert run(runner, script) == run(runner, script)


def test_watch_prints_each_address_and_shot_writes_a_frame(runner):
    shot = os.path.join(OUT_DIR, "runner_shot.rgba")
    if os.path.exists(shot):
        os.remove(shot)
    rows = run(runner, [(0, 10)], "--watch", "3000000,3000004", "--shot", "10", shot)
    assert all(len(r) == 3 for r in rows)
    assert os.path.getsize(shot) == 240 * 160 * 4
