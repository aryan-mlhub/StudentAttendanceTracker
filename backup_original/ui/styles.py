"""
Design system, theme colors, typography, and ttk styling for Student Attendance Tracker.
Modern dark navy and clean slate aesthetic with vibrant accents.
"""

import tkinter as tk
from tkinter import ttk

# --- Design Tokens ---
COLOR_SIDEBAR_BG = "#0F172A"       # Slate 900
COLOR_SIDEBAR_HOVER = "#1E293B"    # Slate 800
COLOR_SIDEBAR_ACTIVE = "#2563EB"   # Royal Blue
COLOR_SIDEBAR_TEXT = "#F8FAFC"     # Slate 50
COLOR_SIDEBAR_MUTED = "#94A3B8"    # Slate 400

COLOR_CONTENT_BG = "#F8FAFC"       # Light Slate
COLOR_CARD_BG = "#FFFFFF"          # Pure White
COLOR_CARD_BORDER = "#E2E8F0"      # Slate 200

COLOR_PRIMARY = "#2563EB"          # Royal Blue
COLOR_PRIMARY_HOVER = "#1D4ED8"    # Darker Blue
COLOR_PRIMARY_LIGHT = "#EFF6FF"    # Blue 50

COLOR_SUCCESS = "#10B981"          # Emerald Green
COLOR_SUCCESS_LIGHT = "#ECFDF5"    # Emerald 50
COLOR_DANGER = "#EF4444"           # Red
COLOR_DANGER_LIGHT = "#FEF2F2"     # Red 50
COLOR_WARNING = "#F59E0B"          # Amber
COLOR_WARNING_LIGHT = "#FFFBEB"    # Amber 50
COLOR_INFO = "#6366F1"             # Indigo

COLOR_TEXT_PRIMARY = "#0F172A"     # Deep Slate
COLOR_TEXT_SECONDARY = "#64748B"   # Cool Grey
COLOR_TEXT_MUTED = "#94A3B8"       # Light Grey

FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 16, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 12, "bold")
FONT_HEADING = (FONT_FAMILY, 10, "bold")
FONT_BODY = (FONT_FAMILY, 10)
FONT_SMALL = (FONT_FAMILY, 9)
FONT_BADGE = (FONT_FAMILY, 9, "bold")
FONT_NAV = (FONT_FAMILY, 11, "normal")
FONT_NAV_ACTIVE = (FONT_FAMILY, 11, "bold")
FONT_STAT_NUM = (FONT_FAMILY, 22, "bold")


def configure_app_styles(root: tk.Tk) -> ttk.Style:
    """Configures global ttk widget styles to match modern theme."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Root background
    root.configure(bg=COLOR_CONTENT_BG)

    # Base Frame styles
    style.configure("TFrame", background=COLOR_CONTENT_BG)
    style.configure("Card.TFrame", background=COLOR_CARD_BG, relief="solid", borderwidth=1)
    style.configure("Sidebar.TFrame", background=COLOR_SIDEBAR_BG)

    # Base Label styles
    style.configure("TLabel", background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_PRIMARY, font=FONT_BODY)
    style.configure("Card.TLabel", background=COLOR_CARD_BG, foreground=COLOR_TEXT_PRIMARY, font=FONT_BODY)
    style.configure("Title.TLabel", background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_PRIMARY, font=FONT_TITLE)
    style.configure("CardTitle.TLabel", background=COLOR_CARD_BG, foreground=COLOR_TEXT_SECONDARY, font=FONT_HEADING)
    style.configure("StatNum.TLabel", background=COLOR_CARD_BG, foreground=COLOR_TEXT_PRIMARY, font=FONT_STAT_NUM)
    style.configure("Muted.TLabel", background=COLOR_CONTENT_BG, foreground=COLOR_TEXT_SECONDARY, font=FONT_SMALL)

    # Treeview (Modern Tables)
    style.configure(
        "Custom.Treeview",
        background=COLOR_CARD_BG,
        foreground=COLOR_TEXT_PRIMARY,
        fieldbackground=COLOR_CARD_BG,
        rowheight=32,
        font=FONT_BODY,
        borderwidth=0
    )
    style.configure(
        "Custom.Treeview.Heading",
        background="#F1F5F9",
        foreground=COLOR_TEXT_PRIMARY,
        font=FONT_HEADING,
        relief="flat",
        padding=(6, 6)
    )
    style.map(
        "Custom.Treeview.Heading",
        background=[("active", "#E2E8F0")]
    )
    style.map(
        "Custom.Treeview",
        background=[("selected", COLOR_PRIMARY_LIGHT)],
        foreground=[("selected", COLOR_PRIMARY)]
    )

    # Entry styles
    style.configure(
        "TEntry",
        padding=6,
        relief="flat",
        font=FONT_BODY
    )

    # Combobox styles
    style.configure(
        "TCombobox",
        padding=5,
        font=FONT_BODY
    )

    # Button styles
    style.configure(
        "Primary.TButton",
        background=COLOR_PRIMARY,
        foreground="#FFFFFF",
        font=FONT_HEADING,
        padding=(12, 7),
        relief="flat"
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLOR_PRIMARY_HOVER), ("disabled", "#CBD5E1")]
    )

    style.configure(
        "Success.TButton",
        background=COLOR_SUCCESS,
        foreground="#FFFFFF",
        font=FONT_HEADING,
        padding=(12, 7),
        relief="flat"
    )
    style.map(
        "Success.TButton",
        background=[("active", "#059669"), ("disabled", "#CBD5E1")]
    )

    style.configure(
        "Danger.TButton",
        background=COLOR_DANGER,
        foreground="#FFFFFF",
        font=FONT_HEADING,
        padding=(12, 7),
        relief="flat"
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#DC2626"), ("disabled", "#CBD5E1")]
    )

    style.configure(
        "Secondary.TButton",
        background="#E2E8F0",
        foreground=COLOR_TEXT_PRIMARY,
        font=FONT_HEADING,
        padding=(10, 6),
        relief="flat"
    )
    style.map(
        "Secondary.TButton",
        background=[("active", "#CBD5E1")]
    )

    return style
