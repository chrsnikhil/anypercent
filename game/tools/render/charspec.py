"""Character animation sets, shared by the Blender renderer and the converter (pure data).

Each animation is (label, base glTF action, overlay action or None, frames sampled). An overlay replaces
the base action's curves for the bones in OVERLAY_BONES, e.g. walking legs with a chai-holding arm.
"""
PLAYER_FRAME = (64, 96)     # player frames at GBA size: shown as a 64 x 64 sprite over a 64 x 32 one
FEET = (32, 84)             # where the player's origin (the floor under the feet) lands in a frame
DEV_FRAME = (64, 64)        # seated devs, rendered with their desk and laptop cutting them off
DEV_FEET = (32, 48)         # a dev's origin is the seat
CHAR_SCALE = 0.75
DEV_SCALE = 0.72            # seated devs 4% smaller so bun-to-hand (62 px at 0.75) fits a 64 px frame
CROWD_FRAME = (64, 64)      # attendees: walk only, cut to 64 x 64 (sprite memory: six on screen)
CROWD_FEET = (32, 58)
DIRS = 8                    # facing d: 0 down the screen, then clockwise: 2 right, 4 up, 6 left

PLAYER_ANIMS = [("idle", "idle", None, 4), ("walk", "walk", None, 8),
                ("carry_idle", "idle", "holding-right", 4), ("carry_walk", "walk", "holding-right", 8)]
DEV_ANIMS = [("type", "sit", "interact-right", 4), ("tired", "sit", None, 1)]
CROWD_ANIMS = [("walk", "walk", None, 8)]
OVERLAY_BONES = {"holding-right": {"arm-right"},
                 "interact-right": {"arm-left", "arm-right", "head", "torso"}}


def facing_degrees(d):
    """Model rotation for facing d (a Mini Character faces -y at 0 degrees)."""
    return 45 + 45 * d


def frame_names(anims, dirs):
    """Sheet order: every direction, then every animation, then every frame."""
    return ["%s_d%d_f%d" % (label, d, f) for d in dirs for label, _, _, n in anims for f in range(n)]


def offsets(anims):
    """(label -> first frame within one direction, frames per direction)."""
    out, k = {}, 0
    for label, _, _, n in anims:
        out[label] = k
        k += n
    return out, k
