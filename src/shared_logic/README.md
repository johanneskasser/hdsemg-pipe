# hdsemg-shared

Reusable Python components and utilities for working with high-density surface EMG (HD-sEMG) data.

This module contains shared logic used across multiple related projects, such as `hdsemg-pipe` and `hdsemg-select`. It is installable as a standalone Python package.

---

## 📦 Installation

This package lives inside a subdirectory (`src/shared_logic`) of a larger monorepo. It includes its own `setup.py` and can be installed directly via `pip`.

### 🔒 Private Installation via SSH

Ensure your SSH access to GitHub is properly configured:

```bash
ssh -T git@github.com
```

Then install using pip:

```bash
pip install "git+ssh://git@github.com/johanneskasser/hdsemg-pipe.git@BRANCH_NAME#egg=hdsemg-shared&subdirectory=src/shared_logic"
```

Replace `BRANCH_NAME` with the appropriate branch name, for example:

```bash
pip install "git+ssh://git@github.com/johanneskasser/hdsemg-pipe.git@17-implement-subdirectory-for-fileloading-logic-to-share-between-projects-hdsemg-pipe-and-hdsemg-select#egg=hdsemg-shared&subdirectory=src/shared_logic"
```

> You must have access to the repository via SSH. This typically requires that your public SSH key is added to your GitHub account.

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
