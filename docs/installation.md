# Installation Guide

This guide describes the available methods for installing hdsemg-pipe and setting up all required dependencies.

## Prerequisites

Before installing hdsemg-pipe, please ensure you have the following installed:

- Python 3.8 or higher
- Git
- (Optional) Conda package manager

## Installation Methods

There are three ways to install hdsemg-pipe:

1. **PyPI package (recommended for most users)**
2. **Conda environment with PyPI package**
3. **From source**

### Method 1: Install via PyPI

1. **Create a virtual environment (recommended)**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # Linux/macOS
   python -m venv venv
   source venv/bin/activate
   ```
2. **Install hdsemg-pipe**
   ```bash
   pip install hdsemg-pipe
   ```

### Method 2: Install via Conda with PyPI package

This method uses Conda to manage the core dependencies while installing hdsemg-pipe from PyPI.

1. **Download the environment file**
   ```bash
   wget https://raw.githubusercontent.com/johanneskasser/hdsemg-pipe/main/environment-pypi.yml
   ```
   Or download `environment.yml` directly from the repository.

2. **Create and activate Conda environment**
   ```bash
   conda env create -f environment.yml
   conda activate hdsemg-pipe
   ```

The environment will automatically install hdsemg-pipe and all its dependencies.

### Method 3: Install from Source

1. **Clone the repository**
   ```bash
   git clone https://github.com/johanneskasser/hdsemg-pipe.git
   cd hdsemg-pipe
   ```
2. **Create a virtual environment (recommended)**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # Linux/macOS
   python -m venv venv
   source venv/bin/activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

#### Alternative: Install with Conda

1. **Clone the repository**
   ```bash
   git clone https://github.com/johanneskasser/hdsemg-pipe.git
   cd hdsemg-pipe
   ```
2. **Create and activate Conda environment**
   ```bash
   conda env create -f environment.yml
   conda activate hdsemg-pipe
   ```

## Compile Resources (only for Source Installation)

After installing the dependencies, you need to compile the Qt resources:

1. **Change to the source directory**
   ```bash
   cd ./hdsemg_pipe
   ```
2. **Compile resources**
   ```bash
   pyrcc5 img.qrc -o resources_rc.py
   ```

## Start Application

After installation, you can start the application with the following command:

```bash
python hdsemg_pipe/main.py
```

## Additional Components

### External Applications

hdsemg-pipe requires two external applications:

1. **hdsemg-select App**
   - Required for Channel Cleaning
   - Installation: [hdsemg-select repository](https://github.com/johanneskasser/hdsemg-select.git)
   - Path configuration in settings after installation

2. **OpenHD-EMG**
   - Required for visualizing Decomposition results
   - Installation: [openhdemg repository](https://github.com/GiacomoValliPhD/openhdemg)
   - Path to virtual environment configuration in settings

## Post-installation: Configuration

1. **Start the application**
   - Launch hdsemg-pipe as described above
   - The application should open with the main dashboard
2. **Configure settings**
   - Open settings from the top menu
   - Set working directory
   - Configure paths to external applications
   - Set logging level

## Verification

1. **Check dependencies**
   ```bash
   pip list  # or conda list if using Conda
   ```
2. **Test resource compilation** (only for Source Installation)
   - Check if `resources_rc.py` was created in the src directory
   - Look for compilation errors
3. **Check external applications**
   - Test hdsemg-select App path
   - Check OpenHD-EMG environment

## Troubleshooting

### Common Installation Issues

1. **Missing dependencies**
   - Error: `ModuleNotFoundError`
   - Solution: Install all requirements
   ```bash
   pip install -r requirements.txt --upgrade
   ```
2. **Resource compilation fails**
   - Error: `pyrcc5 command not found`
   - Solution: Install PyQt5 tools
   ```bash
   pip install pyqt5-tools
   ```
3. **Virtual environment issues**
   - Problem: Incorrect Python version
   - Solution: Create a new environment with the correct version
   ```bash
   python -m venv venv --clear
   ```
4. **hdsemg-shared lib not found (only for Conda)**
   - Error: `ImportError: hdsemg-shared not found`
   - Solution:
     - Remove the hdsemg-shared package from environment.yml and reinstall.
     - After successful installation, the package can be installed with pip:
   ```bash
   pip install hdsemg-shared
   ```

### Getting Help

For installation issues:
1. Check error messages
2. Read the [documentation](https://github.com/johanneskasser/hdsemg-pipe)
3. Open an issue on GitHub with:
   - System information
   - Installation method used
   - Complete error message
   - Steps to reproduce
