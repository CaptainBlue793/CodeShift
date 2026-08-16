"""Tokyo Night as a Pygments style, for the dashboard's code panes.

Pygments ships 49 styles and Tokyo Night is not among them, so it is defined
here rather than approximated with a near-miss like `one-dark`. Keeping it in
its own module means the palette is one readable table instead of hex codes
scattered through a stylesheet — change a constant below and every code pane
follows, because all three columns share one renderer.

Colours are the upstream Tokyo Night (Night variant) palette. `LAVENDER` is the
theme's own purple, and the dashboard's accent colour is deliberately the same
value: the syntax highlighting and the page's own furniture then read as one
design rather than two that happen to sit next to each other.
"""
from __future__ import annotations

from pygments.style import Style
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
    Token,
)

# --- palette ---------------------------------------------------------------
# The first four are the whole application's chrome as well as the code panes':
# `.streamlit/config.toml` is set from them, so the page background, the sidebar
# and the body text are the same colours the syntax highlighting sits on. A test
# asserts the two stay in step, since a TOML file cannot import this module.
BG = "#1a1b26"          # editor background, and the page background
BG_ELEVATED = "#24283b" # sidebar and raised surfaces
FG = "#c0caf5"          # default foreground — a pale lavender — and body text
FG_DIM = "#a9b1d6"      # secondary text: captions, labels, subtitles
GUTTER = "#565f89"      # line numbers, and comments
LAVENDER = "#bb9af7"    # keywords — and the dashboard's accent
BLUE = "#7aa2f7"        # functions, decorators
CYAN = "#2ac3de"        # types, classes, builtins
TEAL = "#73daca"        # regex, escapes
GREEN = "#9ece6a"       # strings
ORANGE = "#ff9e64"      # numbers, constants
YELLOW = "#e0af68"      # parameters
RED = "#f7768e"         # errors, deletions
OPERATOR = "#89ddff"    # punctuation that carries meaning


class TokyoNight(Style):
    """The palette above, mapped onto Pygments' token tree."""

    name = "tokyo-night"
    background_color = BG
    highlight_color = "#292e42"
    line_number_color = GUTTER

    styles = {
        Token: FG,
        Text: FG,
        Text.Whitespace: GUTTER,

        Comment: f"italic {GUTTER}",
        Comment.Preproc: LAVENDER,
        Comment.Special: f"italic {RED}",

        Keyword: LAVENDER,
        Keyword.Constant: ORANGE,
        Keyword.Declaration: LAVENDER,
        Keyword.Namespace: LAVENDER,
        Keyword.Reserved: LAVENDER,
        Keyword.Type: CYAN,

        Name: FG,
        Name.Attribute: BLUE,
        Name.Builtin: CYAN,
        Name.Builtin.Pseudo: ORANGE,
        Name.Class: CYAN,
        Name.Constant: ORANGE,
        Name.Decorator: BLUE,
        Name.Entity: ORANGE,
        Name.Exception: CYAN,
        Name.Function: BLUE,
        Name.Function.Magic: BLUE,
        Name.Label: BLUE,
        Name.Namespace: FG,
        Name.Other: FG,
        Name.Tag: LAVENDER,
        Name.Variable: FG,
        Name.Variable.Magic: ORANGE,

        Literal: ORANGE,
        String: GREEN,
        String.Doc: f"italic {GUTTER}",
        String.Escape: TEAL,
        String.Interpol: FG,
        String.Regex: TEAL,
        String.Symbol: ORANGE,
        Number: ORANGE,

        Operator: OPERATOR,
        Operator.Word: LAVENDER,
        Punctuation: FG,

        Error: f"bg:{RED} {BG}",
        Generic.Deleted: RED,
        Generic.Inserted: GREEN,
        Generic.Heading: f"bold {BLUE}",
        Generic.Subheading: f"bold {LAVENDER}",
        Generic.Emph: "italic",
        Generic.Strong: "bold",
        Generic.Error: RED,
    }
