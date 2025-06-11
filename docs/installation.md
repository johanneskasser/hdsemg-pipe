# Installation Guide

This guide will walk you through the process of installing hdsemg-pipe and setting up all required dependencies.

## Prerequisites

Before installing hdsemg-pipe, ensure you have:

- Python 3.8 or higher installed
- Git installed on your system
- (Optional) Conda package manager

## Installation Methods

There are two main methods to install hdsemg-pipe: using pip with a virtual environment or using Conda.

### Method 1: Installation with pip

1. **Clone the Repository**
   ```bash
   git clone https://github.com/johanneskasser/hdsemg-pipe.git
   cd hdsemg-pipe
   ```

2. **Create a Virtual Environment** (Recommended)
   ```bash
   # On Windows
   python -m venv venv
   venv\Scripts\activate

   # On Linux/macOS
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Method 2: Installation with Conda

1. **Clone the Repository**
   ```bash
   git clone https://github.com/johanneskasser/hdsemg-pipe.git
   cd hdsemg-pipe
   ```

2. **Create and Activate Conda Environment**
   ```bash
   conda env create -f environment.yml
   conda activate hdsemg-pipe
   ```

## Compile Resources

After installing dependencies, you need to compile the Qt resources:

1. **Navigate to the Source Directory**
   ```bash
   cd ./src
   ```

2. **Compile Resources**
   ```bash
   pyrcc5 img.qrc -o resources_rc.py
   ```

## Running the Application

After installation, you can run the application using:

```bash
python src/main.py
```

## Additional Components

### External Applications

hdsemg-pipe requires two external applications to be installed and configured:

1. **hdsemg-select App**
   - Required for channel cleaning
   - Install from [hdsemg-select repository](https://github.com/johanneskasser/hdsemg-select.git)
   - Configure path in Settings after installation

2. **OpenHD-EMG**
   - Required for decomposition result visualization
   - Install from [openhdemg repository](https://github.com/GiacomoValliPhD/openhdemg)
   - Configure virtual environment path in Settings

## Post-Installation Configuration

After installing hdsemg-pipe and its components:

1. **Launch the Application**
   - Start hdsemg-pipe using the command above
   - The application should open with the main dashboard

2. **Configure Settings**
   - Open Settings from the top menu
   - Set the working directory path
   - Configure paths to external applications
   - Set desired logging level

## Verification

To verify your installation:

1. **Check Dependencies**
   ```bash
   pip list  # or conda list if using conda
   ```

2. **Test Resource Compilation**
   - Ensure `resources_rc.py` was created in the src directory
   - Check for any compilation errors

3. **Verify External Applications**
   - Test hdsemg-select app path
   - Verify OpenHD-EMG environment

## Troubleshooting

### Common Installation Issues

1. **Missing Dependencies**
   - Error: `ModuleNotFoundError`
   - Solution: Verify all requirements are installed
   ```bash
   pip install -r requirements.txt --upgrade
   ```

2. **Resource Compilation Fails**
   - Error: `pyrcc5 command not found`
   - Solution: Install PyQt5 tools
   ```bash
   pip install pyqt5-tools
   ```

3. **Virtual Environment Issues**
   - Problem: Wrong Python version
   - Solution: Create new environment with correct version
   ```bash
   python -m venv venv --clear
   ```
4. **hdsemg-shared lib not found (only in conda)**
   - Error: `ImportError: hdsemg-shared not found`
   - Solution: 
     - remove the hdsemg-shared package from the environment.yml and retry installation.
     - After a successful installation, you can install the hdsemg-shared package with pip:
   ```bash
   pip install hdsemg-shared
   ```

### Getting Help

If you encounter installation problems:
1. Check the error messages
2. Review the [documentation](https://github.com/johanneskasser/hdsemg-pipe)
3. Open an issue on GitHub with:
   - Your system information
   - Installation method used
   - Complete error message
   - Steps to reproduce the issue
