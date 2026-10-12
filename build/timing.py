"""Shared timeline constants (video + audio)."""
# =====================================================================
# VOICE-OVER placement: id -> (block, local_from, local_to, global_at_local_from)
# =====================================================================
VO = {
    "v1":  ("01", 0.00, 7.39, 0.30),
    "v2":  ("02", 0.00, 6.77, 8.75),
    "v3a": ("03", 0.00, 2.87, 16.05),
    "v3b": ("03", 2.87, 7.97, 19.37),
    "v4a": ("04", 0.00, 7.45, 25.15),
    "v4b": ("04", 7.45, 9.33, 32.90),
    "v5a": ("05", 0.00, 4.52, 36.25),
    "v5b": ("05", 4.52, 11.15, 43.95),
    "v6a": ("06", 0.00, 2.35, 51.00),
    "v6b": ("06", 2.35, 11.00, 55.79),
    "v7":  ("07", 0.00, 9.56, 68.50),
    "v8a": ("08", 0.00, 4.00, 79.10),
    "v8b": ("08", 4.00, 8.20, 83.53),
}


def vo(seg, local):
    b, l0, l1, g0 = VO[seg]
    return g0 + (local - l0)


END = 89.30

# speech-active spans (global) for music ducking: from local speech on/off times
SPEECH = [
    (vo("v1", 0.14), vo("v1", 7.20)), (vo("v2", 0.06), vo("v2", 6.59)),
    (vo("v3a", 0.21), vo("v3a", 2.83)), (vo("v3b", 2.91), vo("v3b", 7.78)),
    (vo("v4a", 0.04), vo("v4a", 7.23)), (vo("v4b", 7.70), vo("v4b", 9.02)),
    (vo("v5a", 0.13), vo("v5a", 4.35)), (vo("v5b", 4.72), vo("v5b", 10.95)),
    (vo("v6a", 0.06), vo("v6a", 2.19)), (vo("v6b", 2.51), vo("v6b", 10.80)),
    (vo("v7", 0.11), vo("v7", 9.40)), (vo("v8a", 0.13), vo("v8a", 3.77)),
    (vo("v8b", 4.22), vo("v8b", 7.91)),
]


# key sync points shared by picture and sound
T_SIGN = vo("v1", 5.92)
T_HERN = vo("v2", 6.20)
T_TICKS = [vo("v3a", 1.16) + 0.20 * i for i in range(4)]
T_HAT = vo("v3a", 2.50)
T_WAVE = vo("v5b", 6.44)
T_Q = vo("v5b", 8.87)
T_POT = 83.30
DROP_T = [T_POT + 0.12, T_POT + 0.82, T_POT + 1.52]
FALL = 1.00   # enter 0.35 + hang 0.35 + drop 0.30 -> plop
T_BULK = 88.10
MEMES = [(32.75, 35.95, "homelander"), (40.85, 43.95, "kitten"), (53.45, 55.75, "math"), (64.60, 67.95, "vislava")]
