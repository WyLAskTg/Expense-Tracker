LIGHT_PALETTE = {
    "background": "#f6f8fa",
    "surface": "#ffffff",
    "text": "#24292f",
    "muted": "#57606a",
    "border": "#d0d7de",
    "income": "#18794e",
    "expense": "#b42318",
    "warning": "#9a6700",
    "accent": "#0969da",
}

DARK_PALETTE = {
    "background": "#1f2328",
    "surface": "#2d333b",
    "text": "#f0f3f6",
    "muted": "#adbac7",
    "border": "#444c56",
    "income": "#57ab5a",
    "expense": "#e5534b",
    "warning": "#c69026",
    "accent": "#539bf5",
}


def palette_for(theme_name):
    return DARK_PALETTE if theme_name == "Dark" else LIGHT_PALETTE
