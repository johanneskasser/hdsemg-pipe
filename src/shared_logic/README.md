# hdsemg-shared

Reusable Python components and utilities for working with high-density surface EMG (HD-sEMG) data.

This module contains shared logic used across multiple related projects, such as `hdsemg-pipe` and `hdsemg-select`. It is installable as a standalone Python package.

---

## 📦 Installation

This package lives inside a subdirectory (`src/shared_logic`) of a larger monorepo. It includes its own `setup.py` and can be installed directly via `pip`.

```bash
    python.exe -m pip install --upgrade pip 
    pip install hdsemg-shared
```

---

## 🧪 Local Development

If you're actively developing or testing the module locally, you can install it in editable mode:

```bash
cd path/to/hdsemg-pipe/src/shared_logic
pip install -e .
```

This will allow you to make code changes without reinstalling the package.

---

## 🧰 Requirements

This module requires:

- Python ≥ 3.7
- `numpy`
- `scipy`

These will be installed automatically via `install_requires` if not already present in your environment.
