"""device/gpio_buttons.py: which keys the hardware buttons hold down (the GPIO side needs a Pi)."""
import importlib.util
import os

from conftest import LAUNCHER_DIR

spec = importlib.util.spec_from_file_location("gpio_buttons", os.path.join(os.path.dirname(LAUNCHER_DIR), "device", "gpio_buttons.py"))
gb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gb)
ESC, L, R, A = 1, 30, 31, 45


def test_each_button_holds_its_own_key():
    assert gb.keys_for({"A"}) == {A}
    assert gb.keys_for(set()) == set()


def test_l_and_r_together_also_hold_escape():
    """L + R quits to the launcher, the same as on the touch overlay and a Bluetooth pad."""
    assert gb.keys_for({"L", "R"}) == {L, R, ESC}
    assert ESC not in gb.keys_for({"L"}) and ESC not in gb.keys_for({"R"})


def test_y_still_means_escape_on_its_own():
    assert ESC in gb.keys_for({"Y"})


def test_the_keyboard_registers_esc_to_s_so_udev_calls_it_a_keyboard():
    """udev tags ID_INPUT_KEYBOARD only with the keys from Esc to S; RetroArch's udev driver needs that tag."""
    assert set(range(1, 32)) <= gb.KEYBOARD_KEYS
