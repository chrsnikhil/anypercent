import json
import os

from PIL import Image, ImageStat

import build_library as bl
from conftest import FRAME, frame


def test_game_id_matches_the_sandbox_rule():
    assert bl.game_id("Europa rescue!") == "europa-rescue"
    assert bl.game_id("GB Corp.") == "gb-corp"
    assert bl.game_id("Libbet and the Magic Floor") == "libbet-and-the-magic-floor"


def test_detail_is_zero_for_a_blank_frame_and_positive_for_a_pattern():
    assert bl.detail(frame("blank")) == 0
    assert bl.detail(frame("checker")) > 0.05


def test_spread_keeps_first_and_last():
    assert bl.spread([4, 5, 6, 7, 8, 9, 10, 11], 3) == [4, 8, 11]
    assert bl.spread([4, 5], 3) == [4, 5]


def test_rom_choice_prefers_the_sandbox_build(sandbox_games):
    games = bl.build(sandbox_games[0], sandbox_games[1], os.path.join(os.path.dirname(sandbox_games[0]), "lib"),
                     picks_path=None)
    by = {g["id"]: g for g in games}
    assert by["alpha-quest"]["rom"].endswith(os.path.join("built", "alpha-quest.gb"))
    assert by["alpha-quest"]["rom_origin"] == "built"
    assert by["beta-blocks"]["rom_origin"] == "author" and by["beta-blocks"]["rom"].endswith(".gbc")
    assert by["gamma"]["rom"] is None and by["gamma"]["rom_origin"] == "missing"


def test_art_rules(sandbox_games, tmp_path):
    out = tmp_path / "lib"
    games = {g["id"]: g for g in bl.build(sandbox_games[0], sandbox_games[1], str(out), picks_path=None)}
    alpha = games["alpha-quest"]
    tile = Image.open(out / alpha["tile"]).convert("RGB")
    assert tile.tobytes() == frame("checker").tobytes()          # most detailed of the first four
    assert len(alpha["shots"]) == 3                               # spread over the distinct later frames
    bg = Image.open(out / alpha["bg"]).convert("L")
    assert bg.size == bl.BG_SIZE
    assert ImageStat.Stat(bg).mean[0] < 0.4 * 255                  # darkened
    assert len(games["beta-blocks"]["shots"]) == 1                # identical frames collapse to one
    assert games["gamma"]["tile"] is None and games["gamma"]["shots"] == [] and games["gamma"]["bg"] is None


def test_overrides_win(sandbox_games, tmp_path):
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps({"alpha-quest": {"tile": 5, "bg": 4, "shots": [6]}}))
    out = tmp_path / "lib"
    alpha = {g["id"]: g for g in bl.build(sandbox_games[0], sandbox_games[1], str(out), str(picks))}["alpha-quest"]
    tile = Image.open(out / alpha["tile"]).convert("RGB")
    assert tile.getpixel((0, 0)) != (255, 255, 255) or tile.getpixel((2, 0)) != (255, 255, 255)   # a stripes frame
    assert len(alpha["shots"]) == 1


def test_library_json_is_sorted_and_rebuilds_cleanly(sandbox_games, tmp_path):
    out = tmp_path / "lib"
    bl.build(sandbox_games[0], sandbox_games[1], str(out), picks_path=None)
    bl.build(sandbox_games[0], sandbox_games[1], str(out), picks_path=None)
    data = json.load(open(out / "library.json", encoding="utf-8"))
    titles = [g["title"] for g in data["games"]]
    assert titles == sorted(titles, key=str.casefold)
    assert data["version"] == 1


def test_override_can_take_art_from_the_authors_rom_strip(sandbox_games, tmp_path):
    from conftest import save_strip
    games_dir = sandbox_games[1]
    save_strip(os.path.join(games_dir, "boot", "alpha-quest.official.strip.png"), [frame("stripes", (0, 150, 0))] * 12)
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps({"alpha-quest": {"strip": "official", "tile": 0}}))
    out = tmp_path / "lib"
    alpha = {g["id"]: g for g in bl.build(sandbox_games[0], games_dir, str(out), str(picks))}["alpha-quest"]
    tile = Image.open(out / alpha["tile"]).convert("RGB")
    assert tile.getpixel((0, 0)) == (0, 150, 0)                   # the author's strip, not the rebuilt one
    assert alpha["rom_origin"] == "built"                          # the ROM choice is unchanged


def test_bad_override_indices_fall_back_to_the_automatic_pick(sandbox_games, tmp_path):
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps({"alpha-quest": {"tile": 40, "bg": -3, "shots": [6, 99, "x"]}}))
    out = tmp_path / "lib"
    alpha = {g["id"]: g for g in bl.build(sandbox_games[0], sandbox_games[1], str(out), str(picks))}["alpha-quest"]
    tile = Image.open(out / alpha["tile"]).convert("RGB")
    assert tile.tobytes() == frame("checker").tobytes()          # the automatic tile, not a crash
    assert len(alpha["shots"]) == 1                               # only the valid index, 6
    assert alpha["bg"] is not None


def test_the_arcade_field_passes_through(sandbox_games, tmp_path):
    games_json, games_dir = sandbox_games
    meta = json.load(open(games_json, encoding="utf-8"))
    meta["games"][0]["arcade"] = {"id": "ALPH", "replay": "/x/arcade_replay"}
    open(games_json, "w", encoding="utf-8").write(json.dumps(meta))
    games = {g["id"]: g for g in bl.build(games_json, games_dir, str(tmp_path / "lib"), picks_path=None)}
    assert games["alpha-quest"]["arcade"] == {"id": "ALPH", "replay": "/x/arcade_replay"}
    assert "arcade" not in games["gamma"]


def test_a_lineup_keeps_only_those_games(sandbox_games, tmp_path):
    games = bl.build(sandbox_games[0], sandbox_games[1], str(tmp_path / "lib"), picks_path=None,
                     lineup=["beta-blocks", "alpha-quest"])
    assert sorted(g["id"] for g in games) == ["alpha-quest", "beta-blocks"]
    on_disk = json.load(open(tmp_path / "lib" / "library.json", encoding="utf-8"))
    assert sorted(g["id"] for g in on_disk["games"]) == ["alpha-quest", "beta-blocks"]


def test_lineup_file_ignores_comments_and_blanks(tmp_path):
    f = tmp_path / "lineup.txt"
    f.write_text("# the booth lineup\nrebound\n\nsnake  # everyone knows it\n", encoding="utf-8")
    assert bl.read_lineup(str(f)) == ["rebound", "snake"]


def test_a_reskinned_games_own_art_is_used(sandbox_games, tmp_path):
    art = tmp_path / "reskin" / "alpha-quest" / "art"
    art.mkdir(parents=True)
    for n, c in (("tile", (255, 0, 0)), ("shot0", (0, 255, 0)), ("shot1", (0, 0, 255)), ("bg", (9, 9, 9))):
        Image.new("RGB", (160, 144) if n != "bg" else (200, 120), c).save(art / f"alpha-quest-{n}.png")
    out = tmp_path / "lib"
    alpha = {g["id"]: g for g in bl.build(sandbox_games[0], sandbox_games[1], str(out), picks_path=None,
                                          art_from=str(tmp_path / "reskin"))}["alpha-quest"]
    assert alpha["shots"] == ["art/alpha-quest-shot0.png", "art/alpha-quest-shot1.png"]
    assert Image.open(out / alpha["tile"]).getpixel((5, 5))[:3] == (255, 0, 0)
    assert Image.open(out / alpha["bg"]).getpixel((5, 5))[:3] == (9, 9, 9)


def test_an_app_entry_passes_through_without_a_rom(sandbox_games, tmp_path):
    games_json, games_dir = sandbox_games
    meta = json.load(open(games_json, encoding="utf-8"))
    meta["games"].append({"title": "Browser", "app": "browser", "platform": "App", "genre": "Web browser",
                          "authors": "Chromium"})
    open(games_json, "w", encoding="utf-8").write(json.dumps(meta))
    games = {g["id"]: g for g in bl.build(games_json, games_dir, str(tmp_path / "lib"), picks_path=None)}
    b = games["browser"]
    assert b["app"] == "browser" and b["rom"] is None and b["rom_origin"] == "app"
    assert "app" not in games["alpha-quest"]


def test_how_to_play_passes_through(sandbox_games, tmp_path):
    games_json, games_dir = sandbox_games
    meta = json.load(open(games_json, encoding="utf-8"))
    entries = meta["games"] if isinstance(meta, dict) else meta
    how = {"goal": "Reach the end.", "controls": [["A", "Jump"]]}
    entries[0]["how_to"] = how
    open(games_json, "w", encoding="utf-8").write(json.dumps(meta))
    games = bl.build(games_json, games_dir, str(tmp_path / "lib"), picks_path=None)
    assert [g for g in games if g.get("how_to") == how]


def test_gameplay_clips_are_copied_in_order(sandbox_games, tmp_path):
    from PIL import Image
    games_json, games_dir = sandbox_games
    clips = tmp_path / "clips" / "alpha-quest"
    clips.mkdir(parents=True)
    for i in (1, 0, 2):                                         # written out of order: listed in order
        Image.new("RGB", (160, 144), (i * 40, 0, 0)).save(clips / f"alpha-quest-clip-{i:02d}.png")
    games = {g["id"]: g for g in bl.build(games_json, games_dir, str(tmp_path / "lib"), picks_path=None,
                                          clips_from=str(tmp_path / "clips"))}
    assert games["alpha-quest"]["clip"] == [f"art/alpha-quest-clip-{i:02d}.png" for i in range(3)]
    assert (tmp_path / "lib" / "art" / "alpha-quest-clip-02.png").exists()
    assert "clip" not in games["beta-blocks"]
