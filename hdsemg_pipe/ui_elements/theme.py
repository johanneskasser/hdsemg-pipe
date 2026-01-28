"""
Central design system for hdsemg-pipe application.
GitHub-inspired modern UI theme with consistent colors, spacing, and components.
"""


class Colors:
    """Color palette for the application."""

    # Neutral colors (GitHub-style)
    GRAY_50 = "#f9fafb"
    GRAY_100 = "#f3f4f6"
    GRAY_200 = "#e5e7eb"
    GRAY_300 = "#d1d5db"
    GRAY_400 = "#9ca3af"
    GRAY_500 = "#6b7280"
    GRAY_600 = "#4b5563"
    GRAY_700 = "#374151"
    GRAY_800 = "#1f2937"
    GRAY_900 = "#111827"

    # GitHub colors
    BG_PRIMARY = "#ffffff"
    BG_SECONDARY = "#f6f8fa"
    BG_TERTIARY = "#f3f4f6"

    BORDER_DEFAULT = "#d0d7de"
    BORDER_MUTED = "#e5e7eb"

    TEXT_PRIMARY = "#24292f"
    TEXT_SECONDARY = "#57606a"
    TEXT_MUTED = "#6b7280"

    # Brand colors
    BLUE_50 = "#eff6ff"
    BLUE_100 = "#dbeafe"
    BLUE_500 = "#3b82f6"
    BLUE_600 = "#2563eb"
    BLUE_700 = "#1d4ed8"
    BLUE_900 = "#1e40af"

    # Success colors
    GREEN_50 = "#f0fdf4"
    GREEN_100 = "#dcfce7"
    GREEN_500 = "#22c55e"
    GREEN_600 = "#16a34a"
    GREEN_700 = "#15803d"
    GREEN_800 = "#166534"
    GREEN_BORDER = "#86efac"

    # Warning colors
    YELLOW_50 = "#fefce8"
    YELLOW_100 = "#fef9c3"
    YELLOW_500 = "#eab308"
    YELLOW_600 = "#ca8a04"

    # Error colors
    RED_50 = "#fef2f2"
    RED_100 = "#fee2e2"
    RED_500 = "#ef4444"
    RED_600 = "#dc2626"
    RED_700 = "#b91c1c"

    # Orange colors
    ORANGE_50 = "#fff7ed"
    ORANGE_100 = "#ffedd5"
    ORANGE_500 = "#f97316"
    ORANGE_600 = "#ea580c"
    ORANGE_700 = "#c2410c"
    ORANGE_800 = "#92400e"


class Spacing:
    """Spacing system (in pixels)."""

    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    XXL = 24
    XXXL = 32


class BorderRadius:
    """Border radius values."""

    SM = "4px"
    MD = "6px"
    LG = "8px"
    XL = "12px"


class Shadows:
    """Box shadow definitions."""

    SM = "0 1px 2px 0 rgba(0, 0, 0, 0.05)"
    MD = "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)"
    LG = "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)"


class Fonts:
    """Font definitions."""

    FAMILY_SANS = "'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif"
    FAMILY_MONO = "'Consolas', 'Monaco', 'Courier New', monospace"

    SIZE_XS = "11px"
    SIZE_SM = "12px"
    SIZE_BASE = "14px"
    SIZE_LG = "16px"
    SIZE_XL = "18px"
    SIZE_XXL = "20px"

    WEIGHT_NORMAL = "normal"
    WEIGHT_MEDIUM = "500"
    WEIGHT_SEMIBOLD = "600"
    WEIGHT_BOLD = "bold"


class Styles:
    """Pre-built style strings for common components."""

    @staticmethod
    def button_primary():
        """Primary action button style."""
        return f"""
            QPushButton {{
                background-color: {Colors.BLUE_600};
                color: white;
                border: none;
                border-radius: {BorderRadius.MD};
                padding: {Spacing.SM}px {Spacing.LG}px;
                font-size: {Fonts.SIZE_BASE};
                font-weight: {Fonts.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background-color: {Colors.BLUE_700};
            }}
            QPushButton:pressed {{
                background-color: {Colors.BLUE_500};
            }}
            QPushButton:disabled {{
                background-color: {Colors.GRAY_300};
                color: {Colors.GRAY_500};
            }}
        """

    @staticmethod
    def button_secondary():
        """Secondary action button style."""
        return f"""
            QPushButton {{
                background-color: {Colors.BG_SECONDARY};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.SM}px {Spacing.LG}px;
                font-size: {Fonts.SIZE_BASE};
            }}
            QPushButton:hover {{
                background-color: {Colors.GRAY_100};
                border-color: {Colors.GRAY_400};
            }}
            QPushButton:pressed {{
                background-color: {Colors.GRAY_200};
            }}
            QPushButton:disabled {{
                background-color: {Colors.GRAY_100};
                color: {Colors.GRAY_400};
            }}
        """

    @staticmethod
    def button_danger():
        """Danger/destructive action button style."""
        return f"""
            QPushButton {{
                background-color: {Colors.RED_600};
                color: white;
                border: none;
                border-radius: {BorderRadius.MD};
                padding: {Spacing.SM}px {Spacing.LG}px;
                font-size: {Fonts.SIZE_BASE};
                font-weight: {Fonts.WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background-color: {Colors.RED_700};
            }}
            QPushButton:pressed {{
                background-color: {Colors.RED_500};
            }}
            QPushButton:disabled {{
                background-color: {Colors.GRAY_300};
                color: {Colors.GRAY_500};
            }}
        """

    @staticmethod
    def button_icon():
        """Icon-only button style (like copy button)."""
        return f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.XS}px {Spacing.SM}px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_BASE};
                min-width: 32px;
                max-width: 32px;
            }}
            QPushButton:hover {{
                background-color: {Colors.GRAY_100};
                border-color: {Colors.GRAY_400};
            }}
            QPushButton:pressed {{
                background-color: {Colors.GRAY_200};
            }}
        """

    @staticmethod
    def card():
        """Card/panel style."""
        return f"""
            QFrame {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.LG};
                padding: {Spacing.LG}px;
            }}
        """

    @staticmethod
    def input_field():
        """Text input field style."""
        return f"""
            QLineEdit, QTextEdit, QPlainTextEdit {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.SM}px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_BASE};
            }}
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border-color: {Colors.BLUE_500};
                outline: 2px solid {Colors.BLUE_100};
            }}
            QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
                background-color: {Colors.GRAY_100};
                color: {Colors.GRAY_500};
            }}
        """

    @staticmethod
    def combobox():
        """Dropdown/combobox style."""
        return f"""
            QComboBox {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.SM}px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_BASE};
            }}
            QComboBox:hover {{
                border-color: {Colors.GRAY_400};
            }}
            QComboBox:focus {{
                border-color: {Colors.BLUE_500};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: {Spacing.SM}px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {Colors.TEXT_SECONDARY};
            }}
        """

    @staticmethod
    def label_heading(size="xl"):
        """Heading label style."""
        font_size = {
            "sm": Fonts.SIZE_BASE,
            "md": Fonts.SIZE_LG,
            "lg": Fonts.SIZE_XL,
            "xl": Fonts.SIZE_XXL,
        }.get(size, Fonts.SIZE_XL)

        return f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {font_size};
                font-weight: {Fonts.WEIGHT_BOLD};
            }}
        """

    @staticmethod
    def label_secondary():
        """Secondary text label style."""
        return f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Fonts.SIZE_BASE};
            }}
        """

    @staticmethod
    def info_box(type="info"):
        """Info/alert box style."""
        styles = {
            "info": (Colors.BLUE_100, Colors.BLUE_500, Colors.BLUE_900),
            "success": (Colors.GREEN_100, Colors.GREEN_600, Colors.GREEN_800),
            "warning": (Colors.YELLOW_100, Colors.YELLOW_600, Colors.YELLOW_600),
            "error": (Colors.RED_100, Colors.RED_600, Colors.RED_700),
        }
        bg, border, text = styles.get(type, styles["info"])

        return f"""
            QLabel {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {BorderRadius.MD};
                padding: {Spacing.MD}px;
                color: {text};
            }}
        """

    @staticmethod
    def progress_bar():
        """Progress bar style."""
        return f"""
            QProgressBar {{
                border: none;
                background-color: {Colors.GRAY_200};
                border-radius: {BorderRadius.SM};
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {Colors.BLUE_600};
                border-radius: {BorderRadius.SM};
            }}
        """

    @staticmethod
    def groupbox():
        """Group box style."""
        return f"""
            QGroupBox {{
                background-color: {Colors.BG_PRIMARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.LG};
                margin-top: {Spacing.MD}px;
                padding-top: {Spacing.LG}px;
                font-weight: {Fonts.WEIGHT_SEMIBOLD};
                font-size: {Fonts.SIZE_BASE};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {Spacing.MD}px;
                padding: 0 {Spacing.SM}px;
                color: {Colors.TEXT_PRIMARY};
            }}
        """


class CodeBoxStyle:
    """Styles specifically for code display boxes."""

    @staticmethod
    def container():
        return f"""
            QFrame {{
                background-color: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.MD};
            }}
        """

    @staticmethod
    def header():
        return f"""
            QFrame {{
                background-color: {Colors.BG_SECONDARY};
                border-bottom: 1px solid {Colors.BORDER_DEFAULT};
                border-top-left-radius: {BorderRadius.MD};
                border-top-right-radius: {BorderRadius.MD};
            }}
        """

    @staticmethod
    def code_edit():
        return f"""
            QTextEdit {{
                background-color: {Colors.BG_PRIMARY};
                border: none;
                border-bottom-left-radius: {BorderRadius.MD};
                border-bottom-right-radius: {BorderRadius.MD};
                padding: {Spacing.MD}px;
                color: {Colors.TEXT_PRIMARY};
                font-family: {Fonts.FAMILY_MONO};
                font-size: {Fonts.SIZE_SM};
            }}
        """
    
    @staticmethod
    def checkbox():
        """Checkbox style matching the design system."""
        return f"""
            QCheckBox {{
                spacing: {Spacing.SM}px;
                color: {Colors.TEXT_PRIMARY};
                font-size: {Fonts.SIZE_BASE};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {Colors.BORDER_DEFAULT};
                border-radius: {BorderRadius.SM};
                background-color: {Colors.BG_PRIMARY};
            }}
            QCheckBox::indicator:hover {{
                border-color: {Colors.BLUE_500};
            }}
            QCheckBox::indicator:checked {{
                background-color: {Colors.BLUE_600};
                border-color: {Colors.BLUE_600};
                /* Optional: Hier könnte ein SVG-Checkmark-Icon rein */
            }}
            QCheckBox:disabled {{
                color: {Colors.GRAY_400};
            }}
            QCheckBox::indicator:disabled {{
                background-color: {Colors.GRAY_100};
                border-color: {Colors.GRAY_300};
            }}
        """


def get_app_stylesheet() -> str:
    """
    Returns a global stylesheet for the application.
    This replaces QPalette to avoid issues with native widgets like checkboxes and comboboxes.
    Includes all component styles from Styles and CodeBoxStyle classes for consistency.
    """
    return f"""
        /* Base widget styles */
        QWidget {{
            background-color: {Colors.BG_PRIMARY};
            color: {Colors.TEXT_PRIMARY};
            font-family: {Fonts.FAMILY_SANS};
            font-size: {Fonts.SIZE_BASE};
        }}
        QMainWindow {{
            background-color: {Colors.BG_PRIMARY};
        }}
        QToolTip {{
            background-color: {Colors.BG_PRIMARY};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            padding: {Spacing.XS}px;
        }}

        /* Menu styles */
        QMenuBar {{
            background-color: {Colors.BG_SECONDARY};
            color: {Colors.TEXT_PRIMARY};
        }}
        QMenuBar::item:selected {{
            background-color: {Colors.BLUE_600};
            color: white;
        }}
        QMenu {{
            background-color: {Colors.BG_PRIMARY};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
        }}
        QMenu::item:selected {{
            background-color: {Colors.BLUE_600};
            color: white;
        }}

        /* Primary button (default) */
        QPushButton {{
            background-color: {Colors.BLUE_600};
            color: white;
            border: none;
            border-radius: {BorderRadius.MD};
            padding: {Spacing.SM}px {Spacing.LG}px;
            font-size: {Fonts.SIZE_BASE};
            font-weight: {Fonts.WEIGHT_MEDIUM};
        }}
        QPushButton:hover {{
            background-color: {Colors.BLUE_700};
        }}
        QPushButton:pressed {{
            background-color: {Colors.BLUE_500};
        }}
        QPushButton:disabled {{
            background-color: {Colors.GRAY_300};
            color: {Colors.GRAY_500};
        }}

        /* Input fields */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {Colors.BG_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.MD};
            padding: {Spacing.SM}px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_BASE};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border-color: {Colors.BLUE_500};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
            background-color: {Colors.GRAY_100};
            color: {Colors.GRAY_500};
        }}

        /* Combobox */
        QComboBox {{
            background-color: {Colors.BG_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.MD};
            padding: {Spacing.SM}px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_BASE};
        }}
        QComboBox:hover {{
            border-color: {Colors.GRAY_400};
        }}
        QComboBox:focus {{
            border-color: {Colors.BLUE_500};
        }}
        QComboBox:disabled {{
            background-color: {Colors.GRAY_100};
            color: {Colors.GRAY_500};
        }}
        QComboBox::drop-down {{
            border: none;
            padding-right: {Spacing.SM}px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid {Colors.TEXT_SECONDARY};
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.BG_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            selection-background-color: {Colors.BLUE_600};
            selection-color: white;
        }}

        /* Checkbox */
        QCheckBox {{
            spacing: {Spacing.SM}px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_BASE};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.SM};
            background-color: {Colors.BG_PRIMARY};
        }}
        QCheckBox::indicator:hover {{
            border-color: {Colors.BLUE_500};
        }}
        QCheckBox::indicator:checked {{
            background-color: {Colors.BLUE_600};
            border-color: {Colors.BLUE_600};
        }}
        QCheckBox:disabled {{
            color: {Colors.GRAY_400};
        }}
        QCheckBox::indicator:disabled {{
            background-color: {Colors.GRAY_100};
            border-color: {Colors.GRAY_300};
        }}

        /* Labels */
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_BASE};
            background-color: transparent;
        }}

        /* Progress bar */
        QProgressBar {{
            border: none;
            background-color: {Colors.GRAY_200};
            border-radius: {BorderRadius.SM};
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {Colors.BLUE_600};
            border-radius: {BorderRadius.SM};
        }}

        /* Group box */
        QGroupBox {{
            background-color: {Colors.BG_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.LG};
            margin-top: {Spacing.MD}px;
            padding-top: {Spacing.LG}px;
            font-weight: {Fonts.WEIGHT_SEMIBOLD};
            font-size: {Fonts.SIZE_BASE};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: {Spacing.MD}px;
            padding: 0 {Spacing.SM}px;
            color: {Colors.TEXT_PRIMARY};
        }}

        /* Scroll areas and bars */
        QScrollArea {{
            border: none;
            background-color: {Colors.BG_PRIMARY};
        }}
        QScrollBar:vertical {{
            background-color: {Colors.BG_SECONDARY};
            width: 12px;
            border-radius: {BorderRadius.SM};
        }}
        QScrollBar::handle:vertical {{
            background-color: {Colors.GRAY_300};
            border-radius: {BorderRadius.SM};
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {Colors.GRAY_400};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background-color: {Colors.BG_SECONDARY};
            height: 12px;
            border-radius: {BorderRadius.SM};
        }}
        QScrollBar::handle:horizontal {{
            background-color: {Colors.GRAY_300};
            border-radius: {BorderRadius.SM};
            min-width: 20px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {Colors.GRAY_400};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        /* Tab widget */
        QTabWidget::pane {{
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.MD};
            background-color: {Colors.BG_PRIMARY};
        }}
        QTabBar::tab {{
            background-color: {Colors.BG_SECONDARY};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            padding: {Spacing.SM}px {Spacing.LG}px;
            border-top-left-radius: {BorderRadius.MD};
            border-top-right-radius: {BorderRadius.MD};
        }}
        QTabBar::tab:selected {{
            background-color: {Colors.BG_PRIMARY};
            border-bottom-color: {Colors.BG_PRIMARY};
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {Colors.GRAY_100};
        }}

        /* Spinbox */
        QSpinBox, QDoubleSpinBox {{
            background-color: {Colors.BG_PRIMARY};
            border: 1px solid {Colors.BORDER_DEFAULT};
            border-radius: {BorderRadius.MD};
            padding: {Spacing.SM}px;
            color: {Colors.TEXT_PRIMARY};
            font-size: {Fonts.SIZE_BASE};
        }}
        QSpinBox:disabled, QDoubleSpinBox:disabled {{
            background-color: {Colors.GRAY_100};
            color: {Colors.GRAY_500};
        }}

        /* Slider */
        QSlider::groove:horizontal {{
            background-color: {Colors.GRAY_200};
            height: 6px;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background-color: {Colors.BLUE_600};
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background-color: {Colors.BLUE_700};
        }}

        /* Frame (card style) */
        QFrame {{
            background-color: {Colors.BG_PRIMARY};
        }}
    """
