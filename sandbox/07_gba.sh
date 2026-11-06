#!/bin/bash
# GBA toolchain for SHIP IT! (game/): the Wonderful toolchain (arm-none-eabi gcc), Butano, the BlocksDS
# mmutil and grit tools Butano calls, a static libmgba for the headless tests, Blender for the art
# renders, and the Kenney CC0 asset packs. Idempotent: each step is skipped when its result exists.
#   bash run.sh 07_gba.sh
set -e
source "$(dirname "$0")/00_env.sh"
WF=/opt/wonderful
BUTANO_REV=dd5cdffc8d343648a0dfecf1e6eb9da952e2c738
MGBA_TAG=0.10.5
MMUTIL_TAG=v1.19.1-blocks          # newer tags need gcc 15's --embed-dir
GRIT_REV=df7a06b8a0f10722a81f1fd319f0afe9ed7e21b5
GCC_MAJOR=16                       # wf-pacman cannot pin old packages; fail loudly if the toolchain moves
KENNEY=$SANDBOX/assets/kenney
mkdir -p "$TOOLS/bin" "$KENNEY"
ln -sf /usr/bin/python3 "$TOOLS/bin/python"        # Butano's tools call `python`

say "Wonderful toolchain"
if [ ! -x $WF/bin/wf-pacman ]; then
  f=$(curl -s https://wonderful.asie.pl/bootstrap/ | grep -oE 'wf-bootstrap-x86_64[^"]*\.tar\.gz' | head -1)
  mkdir -p $WF && curl -fsSL "https://wonderful.asie.pl/bootstrap/$f" | tar -xz -C $WF
fi
export WONDERFUL_TOOLCHAIN=$WF PATH=$WF/bin:$WF/toolchain/gcc-arm-none-eabi/bin:$PATH
if [ ! -x $WF/toolchain/gcc-arm-none-eabi/bin/arm-none-eabi-gcc ]; then
  wf-pacman -Syu --noconfirm wf-tools
  wf-pacman -S --noconfirm target-gba toolchain-gcc-arm-none-eabi-libstdcxx-picolibc
fi
got=$(arm-none-eabi-gcc -dumpversion | cut -d. -f1)
[ "$got" = "$GCC_MAJOR" ] || { echo "arm-none-eabi-gcc $got installed; SHIP IT! was built with $GCC_MAJOR"; exit 1; }

say "Butano"
if [ ! -d $TOOLS/butano ]; then
  git clone -q https://github.com/GValiente/butano $TOOLS/butano
  git -C $TOOLS/butano checkout -q $BUTANO_REV
fi
[ "$(git -C $TOOLS/butano rev-parse HEAD)" = "$BUTANO_REV" ] || { echo "butano is not at $BUTANO_REV"; exit 1; }

BT=$WF/thirdparty/blocksds/core/tools
build_tool() {    # name repo tag: build a BlocksDS tool from source into $BT/<name>/<name>
  local name=$1 repo=$2 tag=$3
  [ -x $BT/$name/$name ] && return 0
  rm -rf /tmp/$name && git clone -q $repo /tmp/$name
  [ "$tag" = HEAD ] || git -C /tmp/$name checkout -q $tag
  make -C /tmp/$name -j8 > /tmp/$name.log 2>&1 || { tail -20 /tmp/$name.log; exit 1; }
  mkdir -p $BT/$name
  cp "$(find /tmp/$name -maxdepth 3 -type f -name $name -perm -u+x | head -1)" $BT/$name/$name
}
say "mmutil and grit"
build_tool mmutil https://github.com/blocksds/mmutil $MMUTIL_TAG
build_tool grit https://github.com/blocksds/grit $GRIT_REV

say "Butano template ROM (smoke test, and the runner tests' ROM)"
if [ ! -f $TOOLS/butano/template/template.gba ]; then
  make -C $TOOLS/butano/template -j8 > /tmp/butano_template.log 2>&1 || { tail -20 /tmp/butano_template.log; exit 1; }
fi

say "libmgba $MGBA_TAG (static, for the headless runner)"
M=$TOOLS/mgba-src
if [ ! -f $M/build/libmgba.a ]; then
  [ -d $M ] || git clone -q --depth 1 --branch $MGBA_TAG https://github.com/mgba-emu/mgba $M
  mkdir -p $M/build && cd $M/build
  cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT=OFF -DBUILD_SDL=OFF -DBUILD_LIBRETRO=OFF -DBUILD_PYTHON=OFF \
    -DBUILD_SHARED=OFF -DBUILD_STATIC=ON -DUSE_FFMPEG=OFF -DUSE_ZLIB=OFF -DUSE_PNG=OFF -DUSE_LIBZIP=OFF \
    -DUSE_MINIZIP=OFF -DUSE_SQLITE3=OFF -DUSE_ELF=OFF -DUSE_LZMA=OFF -DUSE_EDITLINE=OFF -DUSE_DEBUGGERS=OFF \
    -DUSE_GDB_STUB=OFF -DENABLE_SCRIPTING=OFF -DM_CORE_GB=OFF -DUSE_EPOXY=OFF -DBUILD_GL=OFF -DBUILD_GLES2=OFF \
    -DBUILD_GLES3=OFF > /tmp/mgba_cmake.log 2>&1 || { tail -20 /tmp/mgba_cmake.log; exit 1; }
  make -j8 mgba > /tmp/mgba_make.log 2>&1 || { tail -20 /tmp/mgba_make.log; exit 1; }
  cd - > /dev/null
fi

say "Blender (art renders)"
if ! command -v blender > /dev/null; then
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends blender python3-numpy
fi

say "Kenney CC0 packs"
fetch() {    # name url sha256: download a pinned Kenney zip into $KENNEY/<name>
  [ -f $KENNEY/$1/License.txt ] && return 0
  curl -fsSL -A Mozilla/5.0 -o /tmp/$1.zip "$2"
  echo "$3  /tmp/$1.zip" | sha256sum -c --quiet || { echo "$1.zip does not match its pinned sha256"; exit 1; }
  mkdir -p $KENNEY/$1 && unzip -q -o /tmp/$1.zip -d $KENNEY/$1
}
fetch furniture-kit https://kenney.nl/media/pages/assets/furniture-kit/440e0608a4-1677580847/kenney_furniture-kit.zip   e67652d0932cee41683f74711c03d3e192a2af9979ef8e6b237711f5482d46b0
fetch mini-characters https://kenney.nl/media/pages/assets/mini-characters/bfc7e272b4-1774770718/kenney_mini-characters.zip   9e1d48e6d7b8479ebbe84df71eb5bd8e1b3f0da546dea641890dccc8a02d0999
grep -q "CC0" $KENNEY/furniture-kit/License.txt && grep -q "CC0" $KENNEY/mini-characters/License.txt
say "07_gba done"
