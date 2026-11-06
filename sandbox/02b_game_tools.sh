#!/bin/bash
# Extra per-game build tools that some games' builds expect. All open source.
#   jdk          Java, for Tobu Tobu Girl's music compiler (mmlgb). The build
#                compiles it from the game's own pinned copy, so the compiler
#                always matches the game's music driver.
#   imgtogb.py   Simon Larsen's image -> GB tiles converter (Tobu Tobu Girl)
#   sdcc-4.2.0   full SDCC release for GBSDK games (Crossconnect, Wyrmhole)
#   /opt/gbdk    compatibility link: some build scripts hard-code this path
# The JDK comes from Adoptium (GitHub-hosted) because the Ubuntu mirrors are
# unreliable from this network.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
mkdir -p "$TOOLS/bin"

say "JDK (Temurin 21)"
if [ ! -x "$TOOLS/jdk/bin/javac" ]; then
  curl -fsSL -o /tmp/jdk.tgz "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse"
  rm -rf "$TOOLS/jdk"; mkdir -p "$TOOLS/jdk"
  tar -xzf /tmp/jdk.tgz -C "$TOOLS/jdk" --strip-components=1
  rm -f /tmp/jdk.tgz
fi
"$TOOLS/jdk/bin/java" -version 2>&1 | head -1

say "pyimgtogb"
[ -d "$TOOLS/pyimgtogb" ] || git clone -q --depth 1 https://github.com/SimonLarsen/pyimgtogb "$TOOLS/pyimgtogb"
"$SANDBOX/venv/bin/pip" install -q pypng
cat > "$TOOLS/bin/imgtogb.py" <<EOF
#!/bin/bash
exec "$SANDBOX/venv/bin/python" "$TOOLS/pyimgtogb/imgtogb.py" "\$@"
EOF
chmod +x "$TOOLS/bin/imgtogb.py"
"$TOOLS/bin/imgtogb.py" --help 2>&1 | head -1 || true

say "SDCC 4.2.0 (full release, with the libc sources GBSDK games compile in)"
if [ ! -x "$TOOLS/sdcc-4.2.0/bin/sdcc" ]; then
  curl -fsSL -o /tmp/sdcc.tar.bz2 "https://sourceforge.net/projects/sdcc/files/sdcc-linux-amd64/4.2.0/sdcc-4.2.0-amd64-unknown-linux2.5.tar.bz2/download"
  mkdir -p "$TOOLS/sdcc-4.2.0"
  tar -xjf /tmp/sdcc.tar.bz2 -C "$TOOLS/sdcc-4.2.0" --strip-components=1
  rm -f /tmp/sdcc.tar.bz2
fi
"$TOOLS/sdcc-4.2.0/bin/sdcc" --version | head -1

say "/opt/gbdk compatibility link"
[ -e /opt/gbdk ] || ln -s "$TOOLS/gbdk" /opt/gbdk
ls -la /opt/gbdk
