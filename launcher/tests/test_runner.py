import pytest

from arca_launcher.runner import RunResult, Runner, mgba_command, retroarch_command, run_command, write_retroarch_cfg


def test_mgba_paces_by_video_not_audio():
    cmd = mgba_command("/r/game.gb", exe="mgba-qt")
    assert cmd == ["mgba-qt", "-C", "audioSync=0", "-C", "videoSync=1", "/r/game.gb"]


def test_retroarch_command_and_config(tmp_path):
    cfg = tmp_path / "ra" / "arca.cfg"
    write_retroarch_cfg(str(cfg))
    text = cfg.read_text()
    assert 'input_quit_gamepad_combo = "6"' in text and 'audio_sync = "false"' in text   # L + R quits to the launcher
    assert 'input_player1_analog_dpad_mode = "1"' in text                                   # left stick moves like the D-pad
    cmd = retroarch_command("/r/g.gb", "/c/mgba_libretro.so", str(cfg), exe="retroarch", fullscreen=True)
    assert cmd == ["retroarch", "-L", "/c/mgba_libretro.so", "--appendconfig", str(cfg), "--fullscreen", "/r/g.gb"]


def test_runner_writes_the_retroarch_config_before_launching(tmp_path):
    cfg = tmp_path / "arca.cfg"
    r = Runner("retroarch", "/c/core.so", str(cfg), audio_sync=True)
    cmd = r.command("/r/g.gb")
    assert cmd[-1] == "/r/g.gb" and 'audio_sync = "true"' in cfg.read_text()


def test_unknown_emulator_is_rejected():
    with pytest.raises(ValueError):
        Runner("snes9x").command("/r/g.gb")


def test_run_results():
    assert run_command(["true"]) == RunResult(True, 0, None)
    bad = run_command(["sh", "-c", "exit 3"])
    assert not bad.ok and bad.code == 3
    missing = run_command(["/nonexistent/emulator"])
    assert not missing.ok and missing.code is None and "Cannot start" in missing.error


def test_mgba_smooth_adds_the_bilinear_filter():
    cmd = mgba_command("x.gba", exe="mgba-qt", smooth=True)
    assert cmd[-1] == "x.gba" and "resampleVideo=1" in cmd and cmd[cmd.index("resampleVideo=1") - 1] == "-C"
    assert "resampleVideo=1" not in mgba_command("x.gba", exe="mgba-qt")



def test_retroarch_keeps_the_save_next_to_the_rom(tmp_path):
    cfg = tmp_path / "arca.cfg"
    write_retroarch_cfg(str(cfg))
    text = cfg.read_text()
    for line in ('savefiles_in_content_dir = "true"', 'sort_savefiles_enable = "false"',
                 'sort_savefiles_by_content_enable = "false"'):
        assert line in text, line


def test_retroarch_stays_button_only(tmp_path):
    cfg = tmp_path / "ra.cfg"
    write_retroarch_cfg(str(cfg))
    text = cfg.read_text()
    for line in ('menu_mouse_enable = "false"', 'menu_pointer_enable = "false"', 'input_overlay_enable = "false"'):
        assert line in text, line


def cfg_lines(path):
    """key -> value of a RetroArch cfg file."""
    out = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def test_on_screen_controls_off_writes_no_overlay_or_touch(tmp_path):
    cfg = tmp_path / "ra.cfg"
    write_retroarch_cfg(str(cfg), touch_controls=False, overlay="/o/gamepad.cfg")
    c = cfg_lines(cfg)
    assert c["input_overlay_enable"] == "false" and c["input_touch_enable"] == "false"
    assert c["menu_mouse_enable"] == "false" and c["menu_pointer_enable"] == "false"
    assert "input_overlay" not in c


def test_on_screen_controls_on_draws_the_overlay_as_a_picture_only(tmp_path):
    """The touchpad service turns touches into keys; RetroArch only draws the gamepad (no touch, no pointer)."""
    cfg = tmp_path / "ra.cfg"
    write_retroarch_cfg(str(cfg), touch_controls=True, overlay="/o/gamepad.cfg")
    c = cfg_lines(cfg)
    assert c["input_overlay_enable"] == "true" and c["input_overlay"] == "/o/gamepad.cfg"
    assert 0.4 <= float(c["input_overlay_opacity"]) <= 0.5
    assert c["input_touch_enable"] == "false" and c["input_overlay_pointer_enable"] == "false"
    assert c["input_overlay_show_mouse_cursor"] == "false" and c["input_overlay_hide_in_menu"] == "true"
    assert c["input_overlay_auto_scale"] == "false" and c["input_overlay_enable_autopreferred"] == "false"
    assert c["input_overlay_hide_when_gamepad_connected"] == "false"
    assert c["menu_mouse_enable"] == "false" and c["menu_pointer_enable"] == "false"   # games only, not the menu
    assert c["input_quit_gamepad_combo"] == "6"                                        # the rest is unchanged


def test_on_screen_controls_on_without_an_overlay_file_stays_off(tmp_path):
    cfg = tmp_path / "ra.cfg"
    write_retroarch_cfg(str(cfg), touch_controls=True, overlay=None)
    assert cfg_lines(cfg)["input_overlay_enable"] == "false"


def test_runner_follows_the_flag_at_each_launch(tmp_path):
    cfg = tmp_path / "ra.cfg"
    r = Runner("retroarch", "/c/core.so", str(cfg), overlay="/o/gamepad.cfg")
    r.command("/r/g.gba")
    assert cfg_lines(cfg)["input_overlay_enable"] == "false"               # off unless asked
    r.touch_controls = True
    r.command("/r/g.gba")
    assert cfg_lines(cfg)["input_overlay_enable"] == "true"
    r.touch_controls = False
    r.command("/r/g.gba")
    assert cfg_lines(cfg)["input_overlay_enable"] == "false"


class FakePad:
    def __init__(self, log, overlay):
        self.log = log
        log.append(("start", overlay))

    def stop(self):
        self.log.append(("stop",))


def touch_runner(tmp_path, log, emulator="retroarch", on=True, overlay="/o/gamepad.cfg", start=None):
    r = Runner(emulator, "/c/core.so", str(tmp_path / "ra.cfg"), overlay=overlay,
               touchpad=start or (lambda o: FakePad(log, o)))
    r.touch_controls = on
    return r


def test_touchpad_runs_only_while_retroarch_runs(tmp_path, monkeypatch):
    log = []
    monkeypatch.setattr("arca_launcher.runner.run_command", lambda cmd: log.append(("game", cmd[-1])) or RunResult(True, 0))
    assert touch_runner(tmp_path, log).run("/r/g.gba").ok
    assert log == [("start", "/o/gamepad.cfg"), ("game", "/r/g.gba"), ("stop",)]


def test_touchpad_is_stopped_when_the_game_crashes(tmp_path, monkeypatch):
    log = []

    def boom(cmd):
        log.append(("game",))
        raise RuntimeError("emulator blew up")
    monkeypatch.setattr("arca_launcher.runner.run_command", boom)
    with pytest.raises(RuntimeError):
        touch_runner(tmp_path, log).run("/r/g.gba")
    assert log[-1] == ("stop",)
    bad = RunResult(False, 139, "retroarch exited with code 139")
    monkeypatch.setattr("arca_launcher.runner.run_command", lambda cmd: log.append(("game",)) or bad)
    log.clear()
    assert touch_runner(tmp_path, log).run("/r/g.gba") == bad and log[-1] == ("stop",)


def test_no_touchpad_when_the_setting_is_off_or_there_is_no_overlay_or_no_retroarch(tmp_path, monkeypatch):
    log = []
    monkeypatch.setattr("arca_launcher.runner.run_command", lambda cmd: log.append(("game",)) or RunResult(True, 0))
    touch_runner(tmp_path, log, on=False).run("/r/g.gba")
    touch_runner(tmp_path, log, overlay=None).run("/r/g.gba")
    touch_runner(tmp_path, log, emulator="mgba").run("/r/g.gba")
    assert log == [("game",)] * 3


def test_a_touchpad_that_fails_to_start_never_blocks_the_game(tmp_path, monkeypatch):
    log = []
    monkeypatch.setattr("arca_launcher.runner.run_command", lambda cmd: log.append(("game",)) or RunResult(True, 0))

    def broken(overlay):
        raise OSError("no panel")
    assert touch_runner(tmp_path, log, start=broken).run("/r/g.gba").ok and log == [("game",)]



def test_rumble_routes_game_audio_through_the_haptics_pcm(tmp_path):
    cfg = tmp_path / "ra.cfg"
    write_retroarch_cfg(str(cfg), audio_device="anypercent_haptics")
    text = cfg.read_text()
    assert 'audio_driver = "alsa"' in text and 'audio_device = "anypercent_haptics"' in text
    write_retroarch_cfg(str(cfg))
    assert "audio_device" not in cfg.read_text()


def test_the_runner_passes_its_haptics_pcm_on(tmp_path):
    cfg = tmp_path / "ra.cfg"
    r = Runner("retroarch", "/core.so", str(cfg), haptics="anypercent_haptics")
    r.command("/g.gba")
    assert 'audio_device = "anypercent_haptics"' in cfg.read_text()


def test_retroarch_finds_its_cores_so_save_states_work(tmp_path):
    # without the cores and info folders RetroArch cannot match the core to its .info and refuses every state
    cfg = tmp_path / "ra.cfg"
    write_retroarch_cfg(str(cfg))
    text = cfg.read_text()
    assert 'libretro_directory = "/usr/lib/aarch64-linux-gnu/libretro"' in text
    assert 'libretro_info_path = "/usr/share/libretro/info"' in text
    assert 'network_cmd_enable = "true"' in text          # the home key quits it cleanly over UDP (and it saves)


def test_a_game_saves_its_place_on_quit_and_continues_only_when_asked(tmp_path):
    cfg = tmp_path / "ra.cfg"
    write_retroarch_cfg(str(cfg), states=True, resume=False)
    text = cfg.read_text()
    assert 'savestate_auto_save = "true"' in text and 'savestate_auto_load = "false"' in text
    assert 'savestates_in_content_dir = "true"' in text and 'sort_savestates_enable = "false"' in text
    write_retroarch_cfg(str(cfg), states=True, resume=True)
    assert 'savestate_auto_load = "true"' in cfg.read_text()


def test_arcade_runs_never_get_save_states(tmp_path):
    # a state would let a verified run be rewound
    cfg = tmp_path / "ra.cfg"
    write_retroarch_cfg(str(cfg), states=False, resume=True)
    text = cfg.read_text()
    assert 'savestate_auto_save = "false"' in text and 'savestate_auto_load = "false"' in text


def test_the_runner_passes_continue_and_states_through(tmp_path):
    cfg = tmp_path / "ra.cfg"
    r = Runner("retroarch", "/c/mgba_libretro.so", str(cfg))
    r.command("/r/g.gb", resume=True, states=True)
    assert 'savestate_auto_load = "true"' in cfg.read_text()
    r.command("/r/g.gb")
    assert 'savestate_auto_load = "false"' in cfg.read_text()


def test_the_auto_state_lives_next_to_the_rom():
    from arca_launcher.runner import state_path
    assert state_path("/opt/anypercent/games/built/snake.gb") == "/opt/anypercent/games/built/snake.state.auto"
