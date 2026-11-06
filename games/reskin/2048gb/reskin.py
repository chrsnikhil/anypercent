"""2048, web3 edition: a full Game Boy Color reskin of Sanqui's 2048-gb (zlib licence; the altered version says so
on its title screen, and the original credits stay there too). Design "A, Ethereum" from mockups.py.

Reads the untouched source (games/src/2048gb), writes the working copy (games/work/2048gb); `mod.py 2048gb build`
makes the ROM. Rerunnable: it always starts from the original files.

  colour    the game becomes Game Boy Color only. Every board tile's palette follows from its tile number (value n
            uses tiles $n0-$nF), so after the board is drawn an attribute map is built from it, and at vblank one
            general-purpose DMA puts it in VRAM bank 1 before the existing fast tile copy. The CPU runs in double
            speed so both fit in the blanking time (the game is paced by vblank, so it plays at the same speed).
  palettes  8: the board, then the values in pairs that share a palette with background and diamond swapped
            (2/4 lilacs, 8/16 ETH blues, 32/64, 128/256 purples, 512/1024 deep violet with gold numbers,
            2048/4096 gold)
  tiles     every value redrawn: rounded tile, the ETH diamond, a big crisp number; 2048 is a gold ETH coin
  title     a big pixel ETH diamond over "2048", ANY% WEB3 EDITION, PRESS START, the original credits
  text      "Game over!" reads "REKT!", "You win!" "MAINNET!", "Try again" "AGAIN"

  python reskin.py [--preview DIR]"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gbgfx                                      # noqa: E402

SRC = "/opt/arca-sandbox/games/src/2048gb"
WORK = "/opt/arca-sandbox/games/work/2048gb"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# --- colours ------------------------------------------------------------------------------------------------------

BOARD = (28, 31, 58)
NAVY = (20, 22, 43)
EMPTY = (40, 44, 80)
LILAC_TEXT = (138, 146, 178)
WHITE = (255, 255, 255)
INK = (28, 29, 51)
GOLD_INK = (255, 214, 102)

# palette = [index 0 (board), A, B, ink]: the lower value of a pair has background A and diamond B, the higher one
# the other way round
GAME_PALETTES = [
    [BOARD, EMPTY, LILAC_TEXT, WHITE],                             # 0: board, empty cells, score
    [BOARD, (236, 239, 255), (192, 203, 246), INK],                # 1: 2, 4
    [BOARD, (138, 146, 178), (98, 126, 234), WHITE],               # 2: 8, 16
    [BOARD, (69, 74, 117), (123, 63, 228), WHITE],                 # 3: 32, 64
    [BOARD, (159, 107, 255), (92, 46, 180), WHITE],                # 4: 128, 256
    [BOARD, (60, 30, 130), (40, 20, 90), GOLD_INK],                # 5: 512, 1024
    [BOARD, (255, 200, 60), (200, 130, 20), INK],                  # 6: 2048, 4096
    [BOARD, EMPTY, LILAC_TEXT, WHITE],                             # 7: spare
]
TITLE_PALETTES = [
    [NAVY, (192, 203, 246), (98, 126, 234), WHITE],                # 0: the diamond, 2048
    [NAVY, LILAC_TEXT, (69, 74, 117), WHITE],                      # 1: the edition line, credits
    [NAVY, GOLD_INK, (200, 130, 20), WHITE],                       # 2: PRESS START
] + [[NAVY, LILAC_TEXT, (69, 74, 117), WHITE]] * 5
SPRITE_PALETTE = [(0, 0, 0), WHITE, (255, 107, 107), INK]          # 0 is transparent

VALUES = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]   # exponent e = 1..12 uses tiles $(e+1)0-$(e+1)F


def rgb15(c):
    r, g, b = (round(v * 31 / 255) for v in c)
    return r | g << 5 | b << 10


def palette_db(pals):
    return "\n".join("    dw " + ", ".join(f"${rgb15(c):04X}" for c in p) for p in pals)


# --- drawing helpers: images in palette indexes ----------------------------------------------------------------------

def index_image(w, h, fill=0):
    return Image.new("P", (w, h), fill)


def crisp_text(img, xy, text, size, index, anchor="mm", font=BOLD):
    """Text with no antialiasing (a 1-bit mask), in one palette index."""
    f = ImageFont.truetype(font, size)
    d = ImageDraw.Draw(img)
    l, t, r, b = d.textbbox((0, 0), text, font=f, anchor=anchor)
    m = Image.new("1", (r - l + 2, b - t + 2), 0)
    ImageDraw.Draw(m).text((-l + 1, -t + 1), text, font=f, fill=1, anchor=anchor)
    d.bitmap((xy[0] + l - 1, xy[1] + t - 1), m, fill=index)


def diamond(img, cx, top, h, light, dark, outline=None):
    """The ETH logo h px tall, in two palette indexes (and an outline index)."""
    d = ImageDraw.Draw(img)
    w = h * 0.6
    A, L, R, B, C = (cx, top), (cx - w / 2, top + h * 0.56), (cx + w / 2, top + h * 0.56), (cx, top + h * 0.74), \
        (cx, top + h * 0.42)
    d.polygon([A, L, C], fill=light)
    d.polygon([A, R, C], fill=dark)
    d.polygon([L, B, C], fill=dark)
    d.polygon([R, B, C], fill=light)
    L2, R2, B2, D = (cx - w / 2, top + h * 0.64), (cx + w / 2, top + h * 0.64), (cx, top + h * 0.82), (cx, top + h)
    d.polygon([L2, B2, D], fill=light)
    d.polygon([R2, B2, D], fill=dark)
    if outline is not None:
        d.line([A, L, B, R, A], fill=outline)
        d.line([L2, D, R2, B2, L2], fill=outline)


# --- the board tiles ------------------------------------------------------------------------------------------------

def value_tile(v):
    """32 x 32 in palette indexes 0..3 of the value's palette."""
    e = VALUES.index(v)
    bg, accent = (1, 2) if e % 2 == 0 else (2, 1)
    img = index_image(32, 32, 0)
    ImageDraw.Draw(img).rounded_rectangle((1, 1, 30, 30), 4, fill=bg)
    if v >= 2048:
        diamond(img, 16, 3, 20, accent, 3)
        crisp_text(img, (16, 26), str(v), 8, 3)
        return img
    diamond(img, 7, 4, 9, accent, accent)
    size = 16 if v < 100 else 12 if v < 1000 else 9
    crisp_text(img, (17, 18) if v < 1000 else (16, 19), str(v), size, 3)
    return img


def empty_tile():
    img = index_image(32, 32, 0)
    ImageDraw.Draw(img).rounded_rectangle((1, 1, 30, 30), 4, fill=1)
    return img


def tiles_png():
    """The game's tile sheet (32 wide, 4 tiles per row) redrawn: $00 the board, $10-$1F an empty cell, $20-$DF the
    values; $01-$0F and the score text and digits ($E0 on) keep the original shapes, recoloured for the board."""
    orig = Image.open(os.path.join(SRC, "gfx/tiles.png"))
    out = index_image(32, orig.height, 0)
    # the score strip and anything else not redrawn: original paper -> board, darkest ink -> white, greys between
    remap = {0: 3, 1: 2, 2: 0, 3: 0}                              # PNG index (0 darkest) -> board palette index
    for y in range(orig.height):
        for x in range(32):
            out.putpixel((x, y), remap[orig.getpixel((x, y))])
    for y in range(32):                                            # $00-$0F: tile $00 is the board; keep it plain
        for x in range(32):
            out.putpixel((x, y), 0)
    out.paste(empty_tile(), (0, 32))
    for i, v in enumerate(VALUES):
        out.paste(value_tile(v), (0, 64 + 32 * i))
    return out


# --- title ----------------------------------------------------------------------------------------------------------

FONT3x5 = {
    "A": ["###", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": ["###", "#..", "#..", "#..", "###"], "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"], "G": ["###", "#..", "#.#", "#.#", "###"],
    "I": ["###", ".#.", ".#.", ".#.", "###"], "L": ["#..", "#..", "#..", "#..", "###"],
    "N": ["#..#", "##.#", "#.##", "#..#", "#..#"], "O": ["###", "#.#", "#.#", "#.#", "###"],
    "P": ["###", "#.#", "###", "#..", "#.."], "Q": ["###", "#.#", "#.#", "###", "..#"],
    "R": ["##.", "#.#", "##.", "#.#", "#.#"], "S": ["###", "#..", "###", "..#", "###"],
    "T": ["###", ".#.", ".#.", ".#.", ".#."], "U": ["#.#", "#.#", "#.#", "#.#", "###"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."], "W": ["#...#", "#...#", "#.#.#", "#.#.#", ".#.#."],
    "%": ["#..#", "..#.", ".#..", "#..#", "...."], "3": ["###", "..#", ".##", "..#", "###"],
    ".": [".", ".", ".", ".", "#"], "/": ["..#", "..#", ".#.", "#..", "#.."], " ": ["..", "..", "..", "..", ".."],
}


def tiny_text(img, cx, y, text, index):
    width = sum(len(FONT3x5[c][0]) + 1 for c in text) - 1
    x = cx - width // 2
    for c in text:
        for gy, row in enumerate(FONT3x5[c]):
            for gx, ch in enumerate(row):
                if ch == "#":
                    img.putpixel((x + gx, y + gy), index)
        x += len(FONT3x5[c][0]) + 1


def title_image():
    """160 x 144 in title palette colours. Only columns 2-17 of rows 1-16, and row 17, reach the screen (the
    game's fast copy writes those), so everything is drawn there."""
    img = Image.new("RGB", (160, 144), NAVY)
    layer = {}                                                     # palette number -> index image, composited below
    t0 = index_image(160, 144, 0)
    diamond(t0, 80, 10, 74, 1, 2, 3)
    crisp_text(t0, (80, 99), "2048", 27, 3)
    t1 = index_image(160, 144, 0)
    tiny_text(t1, 80, 114, "ANY% WEB3 EDITION", 1)
    tiny_text(t1, 80, 138, "ORIG. G. CIRULLI / PORT SANQUI", 1)
    t2 = index_image(160, 144, 0)
    crisp_text(t2, (80, 127), "PRESS START", 9, 1)
    for n, layer_img in ((0, t0), (1, t1), (2, t2)):
        layer[n] = layer_img
        for y in range(144):
            for x in range(160):
                k = layer_img.getpixel((x, y))
                if k:
                    img.putpixel((x, y), TITLE_PALETTES[n][k])
    return img


def title_tiles(img):
    """The title as tiles + map + attributes. Tile $00 is plain navy (palette 0). Returns (tile bytes, tilemap and
    attribute map, 20 x 18 each)."""
    tiles = [[[0] * 8 for _ in range(8)]]
    seen = {(0, tuple(tuple(r) for r in tiles[0])): 0}
    tmap = [[0] * 20 for _ in range(18)]
    attr = [[0] * 20 for _ in range(18)]
    cells = [(c, r) for r in range(1, 17) for c in range(2, 18)] + [(c, 17) for c in range(20)]
    for c, r in cells:
        block = [[img.getpixel((c * 8 + x, r * 8 + y)) for x in range(8)] for y in range(8)]
        colours = {p for row in block for p in row}
        pal = next((n for n, p in enumerate(TITLE_PALETTES) if colours <= set(p)), None)
        assert pal is not None, f"title cell {c},{r} mixes palettes: {colours}"
        idx = [[TITLE_PALETTES[pal].index(p) for p in row] for row in block]
        key = (pal, tuple(tuple(row) for row in idx))
        if not any(any(row) for row in idx):
            tmap[r][c], attr[r][c] = 0, 0
            continue
        if key not in seen:
            seen[key] = len(tiles)
            tiles.append(idx)
        tmap[r][c], attr[r][c] = seen[key], pal
    assert len(tiles) <= 256, f"title needs {len(tiles)} tiles"
    data = b"".join(gbgfx.tile_to_2bpp(t) for t in tiles)
    return data, tmap, attr


# --- sprites: the end-of-game words -----------------------------------------------------------------------------------

def sprite_word(text, n, fill, outline):
    """A word as n 8x16 sprites (index image n*8 x 16), centred, outlined."""
    img = index_image(n * 8, 16, 0)
    mask = index_image(n * 8, 16, 0)
    crisp_text(mask, (n * 4, 8), text, 12, 1)
    for y in range(16):
        for x in range(n * 8):
            if mask.getpixel((x, y)):
                img.putpixel((x, y), fill)
            elif any(0 <= x + dx < n * 8 and 0 <= y + dy < 16 and mask.getpixel((x + dx, y + dy))
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                img.putpixel((x, y), outline)
    return img


def sprites_2bpp():
    """The sprite sheet: 8x16 sprites are tile pairs (top, bottom) laid two tiles per sprite in tile order.
    "Game over!" is sprites from tile $00 (10), "You win!" from $14 (9), "Try again" from $30 (6)."""
    data = bytearray(open(os.path.join(SRC, "gfx/sprites.2bpp"), "rb").read())
    for first, n, word, fill in ((0x00, 10, "REKT!", 2), (0x14, 9, "MAINNET!", 1), (0x30, 6, "AGAIN", 1)):
        img = sprite_word(word, n, fill, 3)
        for s in range(n):
            for half in (0, 1):
                rows = [[img.getpixel((s * 8 + x, half * 8 + y)) for x in range(8)] for y in range(8)]
                t = first + s * 2 + half
                data[t * 16:(t + 1) * 16] = gbgfx.tile_to_2bpp(rows)
    return bytes(data)


# --- the code -------------------------------------------------------------------------------------------------------

ASM_CGB = """
; ---- Any% web3 edition: Game Boy Color colour -------------------------------------------------------------------

InitCGB:
    ; double speed: the attribute DMA and the fast tile copy both fit in vblank (IE is set again for the title)
    di
    ld a, 1
    ld [rKEY1], a
    xor a
    ld [rIE], a
    ld a, $30
    ld [rJOYP], a
    stop
    ret

; hl = 8 palettes x 4 colours (64 bytes)
LoadBGPalettes:
    ld a, $80
    ld [rBGPI], a
    ld b, 64
.loop
    ld a, [hli]
    ld [rBGPD], a
    dec b
    jr nz, .loop
    ret

LoadOBJPalettes:
    ld a, $80
    ld [rOBPI], a
    ld b, 64
.loop
    ld a, [hli]
    ld [rOBPD], a
    dec b
    jr nz, .loop
    ret

; copy a 20 x 18 attribute map (hl) into VRAM bank 1 at $9800; LCD off
LoadTitleAttrs:
    ld a, 1
    ld [rVBK], a
    ld de, $9800
    ld c, 18
.row
    ld b, 20
.col
    ld a, [hli]
    ld [de], a
    inc de
    dec b
    jr nz, .col
    ld a, e
    add 12
    ld e, a
    jr nc, .samepage
    inc d
.samepage
    dec c
    jr nz, .row
    xor a
    ld [rVBK], a
    ret

; W_TILEMAP (20 x 18) -> W_ATTR (32 x 18): each tile's palette from its tile number's high nibble
BuildAttrs:
    ld hl, W_TILEMAP
    ld de, W_ATTR
    ld c, 18
.row
    ld b, 20
.col
    push hl
    ld a, [hl]
    swap a
    and $0f
    ld l, a
    ld h, 0
    push de
    ld de, AttrByNibble
    add hl, de
    ld a, [hl]
    pop de
    pop hl
    inc hl
    ld [de], a
    inc de
    dec b
    jr nz, .col
    ld a, e
    add 12
    ld e, a
    jr nc, .samepage
    inc d
.samepage
    dec c
    jr nz, .row
    ret

; at vblank, before the fast tile copy: W_ATTR -> VRAM bank 1, one general-purpose DMA (576 bytes)
CopyAttrsDMA:
    ld a, 1
    ld [rVBK], a
    ld a, W_ATTR >> 8
    ld [rHDMA1], a
    xor a
    ld [rHDMA2], a
    ld a, $98
    ld [rHDMA3], a
    xor a
    ld [rHDMA4], a
    ld a, 576 / 16 - 1
    ld [rHDMA5], a
    xor a
    ld [rVBK], a
    ret

; palette per tile-number high nibble: $0x board, $1x empty cells, $2x-$Dx the values in pairs, $Ex-$Fx score
AttrByNibble:
    db 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 0, 0

; game over / win dims the board, a new game brightens it: palettes change only at vblank, so it is a request

ApplyPalRequest:
    ld hl, GamePalettes
    cp 2
    jr nz, .load
    ld hl, GamePalettesDim
.load
    call LoadBGPalettes
    xor a
    ld [H_PALREQ], a
    ret

DimBoard:
    ld a, 2
    ld [H_PALREQ], a
    ret

BrightBoard:
    ld a, 1
    ld [H_PALREQ], a
    ret

GamePalettes:
{game}
GamePalettesDim:
{game_dim}
ObjPalettes:
{obj}
TitlePalettes:
{title}
TitleAttrs:
{title_attrs}
"""


WAITHBLANK_OLD = r"""waithblank: MACRO
.wait\@
    ld a, [rSTAT]
    and %00000011
    and a
    jr nz, .wait\@
    ENDM"""
WAITHBLANK_NEW = r"""waithblank: MACRO
    ld a, [rLCDC]
    bit 7, a
    jr z, .wait\@
.leave\@
    ld a, [rSTAT]
    and %00000011
    jr z, .leave\@
.wait\@
    ld a, [rSTAT]
    and %00000011
    and a
    jr nz, .wait\@
    ENDM"""


def patch_asm(tmap, attr):
    src = open(os.path.join(SRC, "2048.asm"), encoding="latin-1").read()

    def swap(a, b):
        nonlocal src
        assert src.count(a) == 1, (a[:60], src.count(a))
        src = src.replace(a, b)

    # boot: colour on, double speed, title palettes and attributes (the LCD is off here)
    swap("""    call WriteDMACodeToHRAM
""", """    call WriteDMACodeToHRAM
    call InitCGB
    ld hl, TitlePalettes
    call LoadBGPalettes
    ld hl, ObjPalettes
    call LoadOBJPalettes
    ld hl, TitleAttrs
    call LoadTitleAttrs
""")
    # the new title may use all 256 tiles: copy the whole second half too (title.2bpp is padded to 256 tiles)
    swap("""    ld hl, Title+$800
    ld de, $8800
    ld bc, $100
    call CopyData""", """    ld hl, Title+$800
    ld de, $8800
    ld bc, $800
    call CopyData""")
    # the game's palettes once its tiles are in
    swap("""    ld hl, Sprites
    ld de, $8000
    ld bc, $800
    call CopyData""", """    ld hl, Sprites
    ld de, $8000
    ld bc, $800
    call CopyData
    ld hl, GamePalettes
    call LoadBGPalettes""")
    # attributes follow every tilemap update
    swap("""    jr .next
.ret
    ei
    ret""", """    jr .next
.ret
    call BuildAttrs
    ei
    ret""")
    # palette requests (game over dims the board) are served at a vblank with no board copy: the colour DMA, the
    # board copy and 64 palette writes together overrun the blanking time
    swap("""VBlankHandler:
    push af
    push bc
    push de
    push hl
""", """VBlankHandler:
    push af
    push bc
    push de
    push hl
    ld a, [H_FAST_VCOPY]
    and a
    jr nz, .nopal
    ld a, [H_PALREQ]
    and a
    call nz, ApplyPalRequest
.nopal
""")
    # the DMG greyed the board with rBGP at game over and win; on colour that does nothing, so ask for the dim set
    swap("""    ld a, %10010100
    ld [rBGP], a
    xor a
    ld b, 10""", """    ld a, %10010100
    ld [rBGP], a
    call DimBoard
    xor a
    ld b, 10""")
    swap("""    ld a, %10010100
    ld [rBGP], a
    ld a, $14""", """    ld a, %10010100
    ld [rBGP], a
    call DimBoard
    ld a, $14""")
    swap("""    ld a, %11100100
    ld [rBGP], a
    call UpdateTilemap""", """    ld a, %11100100
    ld [rBGP], a
    call BrightBoard
    call UpdateTilemap""")
    swap("""    ld a, %11100100
    ld [rBGP], a
    jp .gameloop""", """    ld a, %11100100
    ld [rBGP], a
    call BrightBoard
    jp .gameloop""")
    # and reach VRAM at the vblank that copies the tiles
    swap("""    jr z, .regular
    call FastVblank""", """    jr z, .regular
    call CopyAttrsDMA
    call FastVblank""")
    # the title tilemap: the new picture's, 20 x 18 (the 18th row is the bottom line, copied every frame)
    a = src.index("TitleTilemap:\n")
    b = src.index("TitleTilemapEnd\n", a)                          # the label, not its use in "ld bc"
    rows = "\n".join("    db " + ", ".join(f"${v:02X}" for v in row) for row in tmap)
    src = src[:a] + "TitleTilemap:\n" + rows + "\n" + src[b:]
    # this rgbasm (0.3.10) wants constants defined before their first use
    src = ("; Any% web3 edition\n"
           "W_ATTR EQU $D000      ; 18 rows x 32: VRAM bank 1's map, built from the tilemap\n"
           "H_PALREQ EQU $FFBC    ; palette request served at vblank: 0 none, 1 bright, 2 dim\n") + src
    src += ASM_CGB.format(game=palette_db(GAME_PALETTES), game_dim=palette_db(
                              [[tuple(round(v * 0.42) for v in c) for c in p] for p in GAME_PALETTES]),
                          obj=palette_db([SPRITE_PALETTE] * 8),
                          title=palette_db(TITLE_PALETTES),
                          title_attrs="\n".join("    db " + ", ".join(str(v) for v in row) for row in attr))
    return src


def main():
    preview = sys.argv[sys.argv.index("--preview") + 1] if "--preview" in sys.argv else None
    tiles = tiles_png()
    grid = [[tiles.getpixel((x, y)) for x in range(32)] for y in range(tiles.height)]
    tdata = gbgfx.tiles_from_indexes(grid, (32 // 8) * (tiles.height // 8))
    open(os.path.join(WORK, "gfx/tiles.2bpp"), "wb").write(tdata)
    timg = title_image()
    title_data, tmap, attr = title_tiles(timg)
    open(os.path.join(WORK, "gfx/title.2bpp"), "wb").write(title_data.ljust(256 * 16, b"\0"))   # 2 x $800 copied
    open(os.path.join(WORK, "gfx/sprites.2bpp"), "wb").write(sprites_2bpp())
    open(os.path.join(WORK, "2048.asm"), "w", encoding="latin-1", newline="\n").write(patch_asm(tmap, attr))
    # the fast copy writes its last rows a chunk per hblank, timed for normal speed; at double speed a chunk ends
    # inside the same hblank and the next would run into mode 3 (writes lost). Wait for a fresh hblank each time.
    const = open(os.path.join(SRC, "constants.asm"), encoding="latin-1").read()
    old = WAITHBLANK_OLD
    assert old in const, "waithblank macro changed"
    open(os.path.join(WORK, "constants.asm"), "w", encoding="latin-1", newline="\n").write(
        const.replace(old, WAITHBLANK_NEW))
    mk = open(os.path.join(SRC, "Makefile")).read()
    assert "rgbfix -p 0xff -jv" in mk
    open(os.path.join(WORK, "Makefile"), "w", newline="\n").write(mk.replace("rgbfix -p 0xff -jv", "rgbfix -p 0xff -C -jv"))
    if preview:
        os.makedirs(preview, exist_ok=True)
        timg.resize((480, 432), Image.NEAREST).save(os.path.join(preview, "title.png"))
        sheet = Image.new("RGB", (32 * 7, 64), BOARD)
        for i, v in enumerate(VALUES):
            t = value_tile(v)
            pal = GAME_PALETTES[1 + i // 2]
            rgb = Image.new("RGB", (32, 32))
            for y in range(32):
                for x in range(32):
                    rgb.putpixel((x, y), pal[t.getpixel((x, y))])
            sheet.paste(rgb, ((i % 6) * 32 + 16, (i // 6) * 32))
        sheet.resize((sheet.width * 4, sheet.height * 4), Image.NEAREST).save(os.path.join(preview, "tiles.png"))
    print(f"2048 reskinned: title {len(title_data) // 16} tiles")


if __name__ == "__main__":
    main()
