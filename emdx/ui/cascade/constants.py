"""Cascade stage constants."""

# Fixed cascade stages
STAGES = ["idea", "prompt", "analyzed", "planned", "done"]
STAGE_EMOJI = {
    "idea": "\U0001f4a1",
    "prompt": "\U0001f4dd",
    "analyzed": "\U0001f50d",
    "planned": "\U0001f4cb",
    "done": "\u2705",
}
NEXT_STAGE = {
    "idea": "prompt",
    "prompt": "analyzed",
    "analyzed": "planned",
    "planned": "done",
}
