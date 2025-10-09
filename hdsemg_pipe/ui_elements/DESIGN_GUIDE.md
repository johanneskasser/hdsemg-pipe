# Design System Guide

This guide explains how to use the hdsemg-pipe design system to create consistent, modern UI components.

## Quick Start

```python
from hdsemg_pipe.ui_elements.theme import Colors, Fonts, Spacing, BorderRadius, Styles
```

## Design System Components

### 1. Colors

Use predefined colors instead of hardcoded hex values:

```python
# ❌ Old way
button.setStyleSheet("background-color: #3b82f6; color: white;")

# ✅ New way
button.setStyleSheet(f"background-color: {Colors.BLUE_600}; color: white;")
```

**Available color categories:**
- **Neutral**: `GRAY_50` through `GRAY_900`
- **GitHub style**: `BG_PRIMARY`, `BG_SECONDARY`, `BORDER_DEFAULT`, `TEXT_PRIMARY`, `TEXT_SECONDARY`
- **Brand**: `BLUE_50` through `BLUE_900`
- **Success**: `GREEN_50` through `GREEN_800`
- **Warning**: `YELLOW_50` through `YELLOW_600`
- **Error**: `RED_50` through `RED_700`

### 2. Spacing

Use consistent spacing values:

```python
# ❌ Old way
layout.setContentsMargins(10, 5, 10, 5)

# ✅ New way
layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
```

**Spacing scale:**
- `XS = 4px`
- `SM = 8px`
- `MD = 12px`
- `LG = 16px`
- `XL = 20px`
- `XXL = 24px`
- `XXXL = 32px`

### 3. Border Radius

Use consistent border radius:

```python
# ❌ Old way
widget.setStyleSheet("border-radius: 6px;")

# ✅ New way
widget.setStyleSheet(f"border-radius: {BorderRadius.MD};")
```

**Border radius scale:**
- `SM = "4px"`
- `MD = "6px"`
- `LG = "8px"`
- `XL = "12px"`

### 4. Fonts

Use consistent typography:

```python
# ❌ Old way
label.setFont(QFont("Arial", 14, QFont.Bold))

# ✅ New way
label.setStyleSheet(Styles.label_heading(size="lg"))
```

**Font sizes:**
- `SIZE_XS = "11px"`
- `SIZE_SM = "12px"`
- `SIZE_BASE = "14px"`
- `SIZE_LG = "16px"`
- `SIZE_XL = "18px"`
- `SIZE_XXL = "20px"`

## Pre-built Styles

Use pre-built style methods for common components:

### Buttons

```python
# Primary action button
button.setStyleSheet(Styles.button_primary())

# Secondary/cancel button
button.setStyleSheet(Styles.button_secondary())

# Danger/delete button
button.setStyleSheet(Styles.button_danger())

# Icon-only button (like copy button)
button.setStyleSheet(Styles.button_icon())
```

### Input Fields

```python
# Text input
line_edit.setStyleSheet(Styles.input_field())

# Dropdown
combo_box.setStyleSheet(Styles.combobox())
```

### Labels

```python
# Heading
title_label.setStyleSheet(Styles.label_heading(size="xl"))  # sizes: sm, md, lg, xl

# Secondary text
subtitle.setStyleSheet(Styles.label_secondary())
```

### Info Boxes

```python
# Info box
info_label.setStyleSheet(Styles.info_box(type="info"))  # types: info, success, warning, error
```

### Other Components

```python
# Card/Panel
frame.setStyleSheet(Styles.card())

# Progress bar
progress.setStyleSheet(Styles.progress_bar())

# Group box
group.setStyleSheet(Styles.groupbox())
```

## Migration Examples

### Example 1: Button Migration

**Before:**
```python
self.btn_process = QPushButton("Process")
self.btn_process.setStyleSheet("""
    QPushButton {
        background-color: #007bff;
        color: white;
        border: none;
        padding: 8px 16px;
    }
""")
```

**After:**
```python
from hdsemg_pipe.ui_elements.theme import Styles

self.btn_process = QPushButton("Process")
self.btn_process.setStyleSheet(Styles.button_primary())
```

### Example 2: Card Container

**Before:**
```python
container = QFrame()
container.setStyleSheet("""
    QFrame {
        background-color: #ffffff;
        border: 1px solid #cccccc;
        border-radius: 8px;
        padding: 16px;
    }
""")
```

**After:**
```python
from hdsemg_pipe.ui_elements.theme import Styles

container = QFrame()
container.setStyleSheet(Styles.card())
```

### Example 3: Custom Component

**Before:**
```python
status_label = QLabel("Success!")
status_label.setStyleSheet("""
    background-color: #d4edda;
    color: #155724;
    border: 1px solid #c3e6cb;
    padding: 10px;
    border-radius: 5px;
""")
```

**After:**
```python
from hdsemg_pipe.ui_elements.theme import Styles

status_label = QLabel("Success!")
status_label.setStyleSheet(Styles.info_box(type="success"))
```

### Example 4: Custom Style with Theme Colors

**Before:**
```python
widget.setStyleSheet("""
    QWidget {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
    }
""")
```

**After:**
```python
from hdsemg_pipe.ui_elements.theme import Colors, BorderRadius

widget.setStyleSheet(f"""
    QWidget {{
        background-color: {Colors.BG_SECONDARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: {BorderRadius.MD};
    }}
""")
```

## Code Box Component

For displaying code with copy functionality (like in MatlabInstallDialog):

```python
from hdsemg_pipe.widgets.MatlabInstallDialog import CodeBox

# Create code box with loading state
code_box = CodeBox(loading=True, title="Command")

# Later, update with actual code
code_box.update_code("cd /path/to/matlab\npython setup.py install")
```

## Best Practices

1. **Always use theme constants** instead of hardcoded values
2. **Use pre-built styles** when available
3. **Maintain consistency** across similar components
4. **Test dark/light themes** if implementing theme switching in the future
5. **Document custom styles** if you create new component patterns

## Component Checklist

When creating or updating a component:

- [ ] Use `Colors.*` instead of hex codes
- [ ] Use `Spacing.*` for margins and padding
- [ ] Use `BorderRadius.*` for rounded corners
- [ ] Use `Fonts.*` for typography
- [ ] Use `Styles.*` pre-built styles where applicable
- [ ] Add hover states for interactive elements
- [ ] Add disabled states where appropriate
- [ ] Test with different content lengths
- [ ] Ensure consistent spacing with surrounding elements

## Further Reading

See these files for examples:
- `hdsemg_pipe/widgets/MatlabInstallDialog.py` - Modern dialog with code boxes
- `hdsemg_pipe/widgets/BaseStepWidget.py` - Updated step widget
- `hdsemg_pipe/ui_elements/theme.py` - Complete design system reference
