"""
Jupyter Notebook Export for HD-sEMG Analysis

This module generates a customized Jupyter notebook and helper Python module
for continued analysis after the hdsemg-pipe workflow completes.
"""
import os
from pathlib import Path
from typing import Dict

from hdsemg_pipe._log.log_config import logger


def export_analysis_notebook(workfolder: str) -> Dict:
    """
    Export analysis notebook and helper module to workfolder.

    Also generates 01_data_export.ipynb for writing MU properties to SQLite.

    Args:
        workfolder: Path to the workfolder

    Returns:
        Dict with 'helper_path', 'notebook_path', 'db_export_notebook_path' on success,
        or 'error' on failure
    """
    try:
        workfolder_path = Path(workfolder)

        # Check if workfolder exists
        if not workfolder_path.exists():
            return {'error': f"Workfolder does not exist: {workfolder}"}

        # Define output paths
        helper_path = workfolder_path / "workfolder_analysis_helper.py"
        notebook_path = workfolder_path / "00_data_analysis.ipynb"
        db_export_path = workfolder_path / "01_data_export.ipynb"

        logger.info(f"Exporting analysis notebook to: {workfolder}")

        # Generate helper module
        generate_helper_module(workfolder, helper_path)
        logger.info(f"Generated helper module: {helper_path}")

        # Generate Jupyter notebook (existing full analysis notebook)
        generate_jupyter_notebook(workfolder, notebook_path)
        logger.info(f"Generated Jupyter notebook: {notebook_path}")

        # Generate DB export notebook (new - writes to SQLite)
        generate_db_export_notebook(workfolder, db_export_path)
        logger.info(f"Generated DB export notebook: {db_export_path}")

        return {
            'helper_path': str(helper_path),
            'notebook_path': str(notebook_path),
            'db_export_notebook_path': str(db_export_path),
        }

    except Exception as e:
        logger.error(f"Failed to export analysis notebook: {e}")
        return {'error': str(e)}


def generate_helper_module(workfolder: str, output_path: Path):
    """
    Generate the Python helper module with folder paths and utilities.

    Args:
        workfolder: Path to the workfolder
        output_path: Where to save the helper module
    """
    from hdsemg_pipe.actions.notebook_templates import HELPER_MODULE_TEMPLATE

    # Generate the helper module content
    helper_content = HELPER_MODULE_TEMPLATE.format(
        workfolder=str(Path(workfolder).resolve())
    )

    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(helper_content)

    logger.info(f"Helper module written: {output_path}")


def generate_jupyter_notebook(workfolder: str, output_path: Path):
    """
    Generate the Jupyter notebook with analysis cells.

    Args:
        workfolder: Path to the workfolder
        output_path: Where to save the notebook
    """
    try:
        import nbformat
        from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell
    except ImportError:
        raise ImportError(
            "nbformat library is required for notebook export. "
            "Install with: pip install nbformat"
        )

    from hdsemg_pipe.actions.notebook_templates import get_notebook_cells

    # Get all cells
    cells_data = get_notebook_cells(workfolder)

    # Create notebook cells
    cells = []
    for cell_data in cells_data:
        if cell_data['cell_type'] == 'markdown':
            cells.append(new_markdown_cell(cell_data['source']))
        elif cell_data['cell_type'] == 'code':
            cells.append(new_code_cell(cell_data['source']))

    # Create notebook
    nb = new_notebook(cells=cells, metadata={
        'kernelspec': {
            'display_name': 'Python 3',
            'language': 'python',
            'name': 'python3'
        },
        'language_info': {
            'name': 'python',
            'version': '3.8.0'
        }
    })

    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        nbformat.write(nb, f)

    logger.info(f"Jupyter notebook written: {output_path}")


def generate_db_export_notebook(workfolder: str, output_path: Path):
    """
    Generate 01_data_export.ipynb - exports MU properties to SQLite.

    Args:
        workfolder: Path to the workfolder (baked into notebook paths)
        output_path: Where to save the notebook
    """
    try:
        import nbformat
        from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell
    except ImportError:
        raise ImportError(
            "nbformat library is required for notebook export. "
            "Install with: pip install nbformat"
        )

    from hdsemg_pipe.actions.notebook_templates import get_db_export_notebook_cells

    # Resolve db_setup path relative to this package
    db_setup_path = Path(__file__).parent.parent.parent / "db_setup"
    if not db_setup_path.exists():
        # Fallback: sibling to workfolder parent
        db_setup_path = Path(workfolder).parent / "db_setup"

    cells_data = get_db_export_notebook_cells(
        workfolder=str(Path(workfolder).resolve()),
        db_setup_path=str(db_setup_path.resolve()),
    )

    cells = []
    for cell_data in cells_data:
        if cell_data['cell_type'] == 'markdown':
            cells.append(new_markdown_cell(cell_data['source']))
        elif cell_data['cell_type'] == 'code':
            cells.append(new_code_cell(cell_data['source']))

    nb = new_notebook(cells=cells, metadata={
        'kernelspec': {
            'display_name': 'Python 3',
            'language': 'python',
            'name': 'python3'
        },
        'language_info': {
            'name': 'python',
            'version': '3.8.0'
        }
    })

    with open(output_path, 'w', encoding='utf-8') as f:
        nbformat.write(nb, f)

    logger.info(f"DB export notebook written: {output_path}")
