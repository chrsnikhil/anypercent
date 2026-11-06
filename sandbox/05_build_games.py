"""
Rebuild every game from source, so each one is proven modifiable.

For each game: fetch its git submodules, detect its toolchain (RGBDS assembly,
GBDK C, or GB Studio), find its build entry point (Makefile, a Makefile in a
subfolder, a build .sh, or a Windows .bat translated to sh), then build a
clean copy with the version its README names first, and otherwise step
through newer-to-older releases until one builds. Toolchain paths go on the
make command line, so Makefiles that hard-code the author's own paths still
find ours.

  games/build/<id>/     the clean build tree (edit + rebuild here)
  games/built/<id>.gb*  the ROM this sandbox built
  games/BUILD_REPORT.md which toolchain each game needed, or why it did not build
"""
import concurrent.futures as cf
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.request

SANDBOX = os.environ.get("SANDBOX", "/opt/arca-sandbox")
TOOLS = os.path.join(SANDBOX, "toolchains")
G = os.path.join(SANDBOX, "games")
VENV_BIN = os.path.join(SANDBOX, "venv", "bin")
PATCHES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "patches")

RGBDS = ["1.0.4", "0.9.4", "0.8.0", "0.7.0", "0.6.1", "0.5.2", "0.4.2", "0.3.10"]
GBDK = ["4.5.0", "4.2.0", "4.1.1", "4.0.6", "4.0.5", "4.0.3"]

# Games whose build needs something this sandbox does not install, with why.
NEEDS = {
    "tobu-tobu-girl-deluxe": "original GBDK 2.96 + SDCC 3.8.0 + custom tools (author: 'a huge mess')",
    "squishy-the-turtle": "original GBDK 2.95 (pre-2020) in its gbdk/ folder",
    "escape-obliterizer-deluxe": "original GBDK 2.95 (pre-2020)",
    "sushi-nights": "the ZGB engine (Zal0/ZGB)",
    "flooder": "GBT Player and its song data (song_Data), which the published repo leaves out",
    "airaki": "the WLA-DX assembler (it is not written for RGBDS)",
    "el-jamon-volador": "its PowerShell build scripts; the author notes only macOS builds a valid ROM",
}


def rgbds_dir(v):
    d = os.path.join(TOOLS, f"rgbds-{v}")
    if v == "1.0.4" and os.path.exists(os.path.join(TOOLS, "rgbds", "rgbasm")):
        return os.path.join(TOOLS, "rgbds")
    if os.path.exists(os.path.join(d, "rgbasm")):
        return d
    os.makedirs(d, exist_ok=True)
    new_name = v.startswith("1.") or v in ("0.9.3", "0.9.4")
    name = "rgbds-linux-x86_64.tar.xz" if new_name else f"rgbds-{v}-linux-x86_64.tar.xz"
    try:
        tmp = d + ".tar.xz"
        urllib.request.urlretrieve(f"https://github.com/gbdev/rgbds/releases/download/v{v}/{name}", tmp)
        with tarfile.open(tmp) as t:
            t.extractall(d)
        os.remove(tmp)
        for f in glob.glob(os.path.join(d, "**", "rgb*"), recursive=True):
            if os.path.isfile(f) and os.access(f, os.X_OK) and os.path.dirname(f) != d:
                shutil.move(f, os.path.join(d, os.path.basename(f)))
    except Exception:                                                        # noqa: BLE001
        # no binary release for old versions: build the tagged source
        src = d + "-src"
        if not os.path.isdir(src):
            subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", f"v{v}",
                            "https://github.com/gbdev/rgbds", src], check=True)
        # old sources predate GCC 10's -fno-common default
        subprocess.run(["make", "-j8", "-C", src, "Q=", "CFLAGS=-O2 -fcommon -w"], capture_output=True, check=True)
        for b in ("rgbasm", "rgblink", "rgbfix", "rgbgfx"):
            if os.path.exists(os.path.join(src, b)):
                shutil.copy(os.path.join(src, b), d)
    return d


def gbdk_dir(v):
    if v == "4.5.0":
        return os.path.join(TOOLS, "gbdk")
    d = os.path.join(TOOLS, f"gbdk-{v}")
    if not os.path.exists(os.path.join(d, "bin", "lcc")):
        tmp = d + ".tgz"
        urllib.request.urlretrieve(
            f"https://github.com/gbdk-2020/gbdk-2020/releases/download/{v}/gbdk-linux64.tar.gz", tmp)
        os.makedirs(d, exist_ok=True)
        with tarfile.open(tmp) as t:
            for m in t.getmembers():
                m.name = m.name.split("/", 1)[1] if "/" in m.name else ""
                if m.name:
                    t.extract(m, d)
        os.remove(tmp)
    return d


def kind_of(src):
    if glob.glob(os.path.join(src, "**", "*.gbsproj"), recursive=True):
        return "gbstudio"
    text = ""
    for pat in ("*akefile*", "*/*akefile*", "*.sh", "*.bat", "*.mk"):
        for f in glob.glob(os.path.join(src, pat)):
            try:
                text += open(f, errors="ignore").read()
            except OSError:
                pass
    if re.search(r"\blcc\b|GBDK|gbdk|png2asset", text):
        return "gbdk"
    if re.search(r"rgbasm|RGBASM|rgblink|RGBDS", text):
        return "rgbds"
    if glob.glob(os.path.join(src, "**", "*.asm"), recursive=True):
        return "rgbds"
    if glob.glob(os.path.join(src, "**", "*.c"), recursive=True):
        return "gbdk"
    return "unknown"


def readme_pins(src):
    txt = ""
    for f in glob.glob(os.path.join(src, "[Rr][Ee][Aa][Dd][Mm][Ee]*")):
        if os.path.isfile(f):
            txt += open(f, errors="ignore").read()
    g = re.findall(r"(?i)GBDK[- ]2020[^0-9]{0,20}v?(4\.\d\.\d)", txt)
    r = re.findall(r"(?i)RGBDS[^0-9]{0,20}v?(0\.\d\.\d|1\.\d\.\d)", txt)
    return [x for x in g if x in GBDK], [x for x in r if x in RGBDS]


TOOL_RE = re.compile(r'(?i)"?(?:[a-z]:)?[^ "]*?(lcc|rgbasm|rgblink|rgbfix|rgbgfx|png2asset)(?:\.exe)?"?(?=\s|$)')
BAT_SKIP = re.compile(r"(?i)^(rem\b|::|echo|pause|cls|if |goto|:|exit|call |del |erase |rmdir|rd |copy |move |cd |"
                      r"title|start |setlocal|endlocal)")


def bat_to_sh(bat, tool_dir):
    """Translate a simple Windows build .bat into sh: plain tool calls, mkdir, SET variables
    (constant ones are substituted, !DELAYED! ones become shell variables) and
    `for /f %%f in ('dir X\\*.c /b') do ( ... )` loops over source files."""
    text = re.sub(r"\^[ \t]*\r?\n", " ", open(bat, errors="ignore").read())      # ^ continues a line
    delayed ={v.upper() for v in re.findall(r"!(\w+)!", text)}
    consts = {}
    out = ["set -e"]

    def conv(l):
        l = l.replace("\\", "/")
        l = re.sub(r"%%~n\w", "$n", l)
        l = re.sub(r"%%\w", "$f", l)
        l = re.sub(r"!(\w+)!", r"${\1}", l)
        l = re.sub(r"%(\w+)%", lambda m: consts.get(m.group(1).upper(), "${%s}" % m.group(1)), l)
        return TOOL_RE.sub(lambda m: os.path.join(tool_dir, m.group(1).lower()), l)

    for line in text.splitlines():
        l = line.strip().lstrip("@").strip()
        if not l:
            continue
        m = re.match(r"(?i)^for /f %%\w in \('dir (\S+) /b'\) do \($", l)
        if m:
            out.append(f'for f in {m.group(1).replace(chr(92), "/")}; do [ -e "$f" ] || continue; '
                       f'n=$(basename "${{f%.*}}")')
            continue
        if l == ")":
            out.append("done")
            continue
        m = re.match(r"(?i)^set\s+(\w+)=(.*)$", l)
        if m:
            name, val = m.group(1), m.group(2)
            if name.upper() in delayed:
                out.append(f'{name}="{conv(val)}"')
            else:
                consts[name.upper()] = val
            continue
        m = re.match(r"(?i)^if not exist \S+ (?:mkdir|md) (\S+)", l)
        if m:
            out.append("mkdir -p " + m.group(1).replace("\\", "/"))
            continue
        if l.lower().startswith(("mkdir ", "md ")):
            out.append("mkdir -p " + re.sub(r"^-p\s+", "", l.split(None, 1)[1]).replace("\\", "/"))
            continue
        if BAT_SKIP.match(l):
            continue
        out.append(conv(l))
    return "\n".join(out) + "\n"


def roms_in(tree):
    return [f for f in glob.glob(os.path.join(tree, "**", "*"), recursive=True)
            if re.search(r"\.gbc?$", f, re.I) and os.path.isfile(f)]


# Per-game build settings. Values may use {TOOLS} and {TC} (the toolchain dir).
#   vars    extra make variables
#   link    {path in tree: target} symlinks for toolchains a Makefile expects in-tree
#   cmd     replaces the detected build command
#   prefer  "bat" when the Makefile is an unused template and the .bat is the real build
#   path    extra PATH entries
#   pre     shell commands run in the tree before the build
GBSDK = dict(path="{TOOLS}/sdcc-4.2.0/bin",               # GBSDK: RGBDS + a full SDCC 4.2.0, whose libc
             vars="LIBC_PATH={TOOLS}/sdcc-4.2.0/share/sdcc/lib/src")    # sources it compiles into the ROM
GAME = {
    # the music compiler must match the music driver, so build it from the game's own pinned mmlgb
    "tobu-tobu-girl": dict(pre="mkdir -p _mmlgb && javac -nowarn -d _mmlgb $(find mmlgb/parser/src -name '*.java')"
                               " && jar cfe _mmlgb/MMLGB.jar dk.hisimon.mmlgb.MMLGB -C _mmlgb dk",
                           vars="MMLGB=_mmlgb/MMLGB.jar"),
    "max-pirate": dict(prefer="bat"),
    "max-pirate-extra-boom": dict(prefer="bat"),
    "crossconnect": GBSDK,
    "wyrmhole": GBSDK,
    # the README's own build steps (no Makefile in the repo)
    "gb-corp": dict(cmd="L={TC}/bin; $L/lcc -Wa-l -Wl-m -Wl-j -c -o gbcorp.o gbcorp.c"
                        " && $L/lcc -Wa-l -Wl-m -Wl-j -c -o music.o music.c"
                        " && $L/sdasgb -plosgff -Ilibc -c -o gbt_player.o gbt_player.s"
                        " && $L/sdasgb -plosgff -Ilibc -c -o gbt_player_bank1.o gbt_player_bank1.s"
                        " && $L/lcc -Wl-yt0x1B -Wl-yo2 -Wl-ya1 -Wm-yn\"GB-Corp\" -Wm-ys -Wm-yc -o gbcorp.gb"
                        " gbcorp.o music.o gbt_player.o gbt_player_bank1.o"),
}

OUT_ERR = re.compile(r"(?i)(?:failed to open output file|cannot open output file|unable to open output file|"
                     r"can't create|cannot create)\s*'?([^'\s:]+)'?")
MISSING_H = re.compile(r"(?m)^(\S+?):\d+(?::\d+)?: fatal error: ([^:\s]+): No such file or directory")
LINK_MISSING = re.compile(r"can't find `([^'/][^']*)'")
INCLUDE = re.compile(rb'(#\s*include\s*["<])([^">\r\n]*)')


def find_ci(root, rel):
    """Resolve rel under root ignoring case (Windows authors), or None."""
    cur = root
    for part in rel.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            cur = os.path.dirname(cur)
            continue
        if not os.path.isdir(cur):
            return None
        hit = [e for e in os.listdir(cur) if e.lower() == part.lower()]
        if not hit:
            return None
        cur = os.path.join(cur, hit[0])
    return cur


def prepare(src, work, gid, apply_patch=True):
    """Clean copy of the source, with prebuilt ROMs removed, Windows-isms fixed and any patch applied."""
    if os.path.exists(work):
        shutil.rmtree(work)
    shutil.copytree(src, work, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    for f in roms_in(work):                     # prebuilt ROMs in the tree do not count
        os.remove(f)
    for f in glob.glob(os.path.join(work, "**", "*"), recursive=True):
        if not os.path.isfile(f) or os.path.islink(f):
            continue
        if f.endswith((".py", ".sh", ".pl")):   # runnable, and no CRLF in shebangs
            data = open(f, "rb").read()
            if b"\r\n" in data:
                open(f, "wb").write(data.replace(b"\r\n", b"\n"))
            os.chmod(f, os.stat(f).st_mode | 0o111)
        elif f.endswith((".c", ".h")):          # #include "..\x.h" -> "../x.h"
            data = open(f, "rb").read()
            fixed = INCLUDE.sub(lambda m: m.group(1) + m.group(2).replace(b"\\", b"/"), data)
            if fixed != data:
                open(f, "wb").write(fixed)
    patch = os.path.join(PATCHES, gid + ".patch")
    if apply_patch and os.path.exists(patch):                # git apply: text and binary (graphics) edits
        r = subprocess.run(["git", "apply", "--whitespace=nowarn", patch], cwd=work, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"patch {gid}.patch did not apply: {(r.stdout + r.stderr)[-300:]}")


def run_build(work, env, cmd, log_path):
    """Run the build. When it fails for a reason a Windows author would not have hit, fix that and rerun:
    a missing output folder is created; a header included with the wrong case gets a correctly
    named link; a header that lives elsewhere in the tree goes on the compiler's include path."""
    logs = []
    env = dict(env)
    cpath = []
    bases = [work] + [os.path.dirname(m) for m in glob.glob(os.path.join(work, "*", "[Mm]akefile"))]
    for _ in range(16):
        try:
            r = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=600, shell=True)
            log = r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            log = "timeout"
        logs.append(f"$ {cmd}\n{log}")
        if roms_in(work):
            break
        made = False
        for path in OUT_ERR.findall(log):
            d = os.path.dirname(path)
            for base in bases:
                full = os.path.join(base, d)
                if d and not os.path.isdir(full):
                    os.makedirs(full, exist_ok=True)
                    made = True
        for path in set(LINK_MISSING.findall(log)):          # linker input named with the wrong case
            for base in bases:
                want = os.path.join(base, path)
                hit = find_ci(base, path)
                if hit and not os.path.lexists(want):
                    os.symlink(os.path.relpath(hit, os.path.dirname(want)), want)
                    made = True
                    break
        if not made and "make -j" in cmd:                     # Makefiles that are not parallel-safe
            cmd = re.sub(r"make -j\d+", "make", cmd)
            made = True
        for srcfile, hdr in set(MISSING_H.findall(log)):
            fixed = False
            for base in bases:
                inc_dir = os.path.dirname(os.path.join(base, srcfile))
                want = os.path.normpath(os.path.join(inc_dir, hdr))
                hit = find_ci(inc_dir, hdr) if os.path.isdir(inc_dir) else None
                if hit and not os.path.exists(want):
                    os.makedirs(os.path.dirname(want), exist_ok=True)
                    os.symlink(os.path.relpath(hit, os.path.dirname(want)), want)
                    fixed = made = True
                    break
            if fixed:
                continue
            tail = hdr.lstrip("./").lower()
            for f in sorted(glob.glob(os.path.join(work, "**", "*"), recursive=True), key=len):
                if f.lower().endswith("/" + tail) and os.path.isfile(f):
                    d = f[: -len(tail) - 1]
                    if d not in cpath:
                        cpath.append(d)
                        env["CPATH"] = ":".join(cpath)
                        made = True
                    break
        if not made:
            break
    full = "\n".join(logs)
    with open(log_path, "w") as f:
        f.write(full)
    new = sorted(roms_in(work), key=lambda f: (-os.path.getsize(f), f))
    # what worked, so mod.py can rebuild an edited copy the same way
    recipe = dict(cmd=cmd, env={k: env[k] for k in ("PATH", "GBDK_HOME", "GBDKDIR", "RGBDS", "CPATH") if k in env})
    return bool(new), new, full, recipe


def first_error(log):
    lines = [l.strip() for l in log.splitlines() if l.strip()]
    errs = [l for l in lines if re.search(r"(?i)\berror\b|not found|no such file|permission denied|undefined", l)
            and not l.startswith("make: *** Waiting")]
    return (errs[0] if errs else (lines[-1] if lines else "?"))[:140]


def build(gid):
    src = os.path.join(G, "src", gid)
    work = os.path.join(G, "build", gid)
    logdir = os.path.join(G, "logs", gid)
    shutil.rmtree(logdir, ignore_errors=True)
    os.makedirs(logdir, exist_ok=True)
    if os.path.exists(os.path.join(src, ".gitmodules")):
        subprocess.run(["git", "-C", src, "submodule", "update", "--init", "--recursive", "--depth", "1", "--quiet"],
                       capture_output=True)
    kind = kind_of(src)
    res = dict(id=gid, kind=kind, ok=False, toolchain=None, rom=None, log="", tries=[], error="")
    if kind == "gbstudio":
        res["log"] = "GB Studio project: edit and build it in GB Studio"
        return res
    cfg = GAME.get(gid, {})
    has_make = any(os.path.exists(os.path.join(src, m)) for m in ("Makefile", "makefile", "GNUmakefile"))
    sub_make = None
    if not has_make:
        cands = sorted(glob.glob(os.path.join(src, "*", "[Mm]akefile")), key=lambda p: ("src" not in p, p))
        cands = [c for c in cands if "/tools/" not in c and "/mmlgb/" not in c]
        sub_make = os.path.relpath(os.path.dirname(cands[0]), src) if cands else None
    scripts = [n for n in ("build.sh", "make.sh", "compile.sh") if os.path.exists(os.path.join(src, n))]
    bats = [b for b in glob.glob(os.path.join(src, "*.bat"))
            if not re.search(r"(?i)clean|debug|pocket", os.path.basename(b))]
    bats.sort(key=lambda p: (not re.search(r"(?i)gameboy|^make|build|compile", os.path.basename(p)), p))
    pin_g, pin_r = readme_pins(src)

    def recipe(tool_dir, make_vars):
        if "cmd" in cfg:
            return cfg["cmd"]
        if bats and cfg.get("prefer") == "bat":
            with open(os.path.join(work, "_arca_build.sh"), "w") as f:
                f.write(bat_to_sh(bats[0], tool_dir))
            return "bash _arca_build.sh"
        if has_make:
            return f"make -j4 {make_vars}"
        if sub_make:
            return f"make -j4 -C {sub_make} {make_vars}"
        if scripts:                              # scripts that hard-code /opt/gbdk get this toolchain
            text = open(os.path.join(work, scripts[0]), errors="ignore").read()
            if kind == "gbdk":
                text = text.replace("/opt/gbdk/", os.path.dirname(tool_dir) + "/")
            with open(os.path.join(work, "_arca_build.sh"), "w") as f:
                f.write(text)
            return f"PATH={tool_dir}:$PATH bash _arca_build.sh"
        if bats:
            with open(os.path.join(work, "_arca_build.sh"), "w") as f:
                f.write(bat_to_sh(bats[0], tool_dir))
            return "bash _arca_build.sh"
        return "make"

    base_env = dict(os.environ)
    base_env["PATH"] = ":".join([os.path.join(TOOLS, "bin"), os.path.join(TOOLS, "jdk", "bin"), VENV_BIN,
                                 base_env["PATH"]])
    versions = (list(dict.fromkeys(pin_r + RGBDS)) if kind == "rgbds" else list(dict.fromkeys(pin_g + GBDK)))
    for n, v in enumerate(versions):
        if kind == "rgbds":
            try:
                d = rgbds_dir(v)
            except Exception:                                                # noqa: BLE001
                res["tries"].append(f"RGBDS {v}: toolchain unavailable")
                continue
            tool_dir = d
            env = dict(base_env, PATH=d + ":" + base_env["PATH"], RGBDS=d + "/")
            mv = f"RGBDS={d}/ RGBASM={d}/rgbasm RGBLINK={d}/rgblink RGBFIX={d}/rgbfix RGBGFX={d}/rgbgfx"
        else:
            d = gbdk_dir(v)
            tool_dir = os.path.join(d, "bin")
            env = dict(base_env, PATH=tool_dir + ":" + base_env["PATH"], GBDK_HOME=d + "/", GBDKDIR=d + "/")
            mv = f"GBDK_HOME={d}/ GBDKDIR={d}/ LCC={d}/bin/lcc"

        def fill(t, d=d):
            return t.replace("{TOOLS}", TOOLS).replace("{TC}", d)
        if "vars" in cfg:
            mv += " " + fill(cfg["vars"])
        if "path" in cfg:
            env["PATH"] = fill(cfg["path"]) + ":" + env["PATH"]
        name = ("RGBDS " if kind == "rgbds" else "GBDK-2020 ") + v
        prepare(src, work, gid)
        for rel, target in cfg.get("link", {}).items():
            p = os.path.join(work, rel)
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            elif os.path.lexists(p):
                os.remove(p)
            os.symlink(fill(target), p)
        cmd = fill(recipe(tool_dir, mv))
        if "pre" in cfg:
            cmd = f"{fill(cfg['pre'])} && {cmd}"
        ok, new, log, how = run_build(work, env, cmd, os.path.join(logdir, f"{n:02d}-{name.replace(' ', '_')}.log"))
        res["tries"].append(f"{name}: {'OK' if ok else 'fail'}")
        if n == 0 or ok:                         # the first (pinned or newest) try explains best
            res["log"], res["error"] = log[-1500:], first_error(log)
        if ok:
            res.update(ok=True, toolchain=name, rom=new[0], build=how, error="")
            break
    for old in glob.glob(os.path.join(G, "built", gid + ".gb*")):     # never leave a stale ROM behind
        os.remove(old)
    if res["ok"]:
        os.makedirs(os.path.join(G, "built"), exist_ok=True)
        dst = os.path.join(G, "built", gid + os.path.splitext(res["rom"])[1].lower())
        shutil.copy(res["rom"], dst)
        res["rom"] = dst
        res["sha256"] = hashlib.sha256(open(dst, "rb").read()).hexdigest()
    return res


def main():
    import sys
    ids = sys.argv[1:] or sorted(os.listdir(os.path.join(G, "src")))
    for v in RGBDS:                              # fetch/build toolchains serially first
        try:
            rgbds_dir(v)
        except Exception as e:                                               # noqa: BLE001
            print(f"  (RGBDS {v} unavailable: {str(e)[:80]})")
    for v in GBDK:
        gbdk_dir(v)
    def safe(gid):
        try:
            return build(gid)
        except Exception as e:                                               # noqa: BLE001
            return dict(id=gid, kind="?", ok=False, toolchain=None, rom=None, log=f"script error: {e}", tries=[])
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(safe, ids))
    bj = os.path.join(G, "build.json")
    if sys.argv[1:] and os.path.exists(bj):          # partial run: merge with earlier results
        done = {r["id"]: r for r in results}
        results = [done.pop(r["id"], r) for r in json.load(open(bj))] + list(done.values())
    json.dump(results, open(bj, "w"), indent=1)
    ok = [r for r in results if r["ok"]]
    with open(os.path.join(G, "BUILD_REPORT.md"), "w") as f:
        f.write(f"# Build report\n\n{len(ok)} of {len(results)} games rebuilt from source in this sandbox. "
                "Every game also has its author-published ROM in games/roms/. "
                "Full logs for every toolchain tried: games/logs/<id>/.\n\n")
        f.write("| Game | Built with | Result |\n|---|---|---|\n")
        for r in results:
            if r["ok"]:
                why = "built"
            elif r["id"] in NEEDS:
                why = "needs " + NEEDS[r["id"]]
            elif r["kind"] == "gbstudio":
                why = "GB Studio project: open in GB Studio"
            else:
                why = "not yet: " + (r.get("error") or "?")[:120].replace("|", "/")
            f.write(f"| {r['id']} | {r['toolchain'] or r['kind']} | {why} |\n")
    for r in results:
        print(f"  {r['id']:28s} {r['kind']:9s} {('OK   ' + r['toolchain']) if r['ok'] else 'FAIL ' + (NEEDS.get(r['id']) or ' / '.join(r['tries'])[-90:])}")
    print(f"\n{len(ok)}/{len(results)} built")


if __name__ == "__main__":
    main()
