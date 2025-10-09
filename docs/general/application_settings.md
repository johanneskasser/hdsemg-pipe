## Application Settings

This section descibes how to configure the application settings in the hdsemg-pipe application. 
The application settings allow you to specify the working directory of the application as described in the [Opening Data](../processing/opening_data.md) section, as well as the path to the external hdsemg-select application and the openhdemg executable.
The settings dialog can be accessed from the top menu bar under **Settings** -> **Preferences**.

![Settings Dialog](../img/settings/settings_dialog.png)

### Channel Selection App
The **Channel Selection App** section allows you to manage the installation of [hdsemg-select](https://github.com/johanneskasser/hdsemg-select), an external application used for channel selection.
By default, the application will install the latest version of hdsemg-select from PyPI. 


### Work Folder
The **Work Folder** section allows you to specify the working directory of the application. This is the directory where all the data will be stored and processed. As soon as you open a file, the application will create a subdirectory in the working directory with the name of the file or folder. Detailed information can be found in the [Opening Data](../processing/opening_data.md) section.

### Line Noise Removal
The **Line Noise Removal** section allows you to configure how powerline interference (50/60 Hz) and harmonics are removed from your EMG signals. This is a new processing step introduced between Grid Association and Region of Interest definition.

#### Power Line Frequency Region
Select your geographic region to automatically configure the correct powerline frequencies:

- **🇺🇸 USA/North America (60 Hz)**: Removes 60, 120, 180, 240 Hz
- **🇪🇺 Europe/Asia (50 Hz)**: Removes 50, 100, 150, 200 Hz

#### Line Noise Removal Method
Choose from multiple filtering methods depending on your needs and available software:

**Available Methods:**

1. **⚡ MNE-Python: Notch Filter (FIR) - Fast**
   - Classic FIR notch filter
   - Very fast processing
   - Good quality
   - No additional software required

2. **⭐ MNE-Python: Spectrum Fit (Adaptive) - Recommended**
   - Adaptive spectrum fitting approach
   - Excellent quality with minimal distortion
   - Similar to CleanLine algorithm
   - No additional software required
   - **This is the default and recommended method**

3. **🏆 MATLAB: CleanLine (EEGLAB Plugin) - Gold Standard**
   - Original CleanLine algorithm from EEGLAB
   - Multi-taper with statistical validation
   - Best quality for time-varying line noise
   - Requires: MATLAB + EEGLAB + CleanLine plugin
   - Slowest but highest quality

4. **🔬 MATLAB: IIR Notch Filter**
   - Native MATLAB implementation
   - Very narrow-band filtering
   - Requires: MATLAB + MATLAB Engine for Python

5. **🐙 Octave: IIR Notch Filter (Free)**
   - MATLAB-compatible, open source
   - Free alternative to MATLAB
   - Requires: GNU Octave + oct2py

#### Installation Status
The settings dialog displays the installation status of optional dependencies:
- ✓ MNE-Python: Always available (required dependency)
- ✓/✗ MATLAB Engine: Shows if MATLAB is detected
- ✓/✗ Octave + oct2py: Shows if Octave is detected

Methods that are not available (due to missing dependencies) will be disabled in the dropdown menu.

#### MATLAB Engine Installation Assistant

The application provides an installation assistant that generates the correct installation commands for your system:

1. Go to **Settings → Preferences → Line Noise Removal**
2. Scroll to the **MATLAB Engine for Python** section
3. Click **Show Installation Instructions** button
4. Follow the displayed instructions:
   - **Option 1 (Recommended)**: Copy the command and run it in MATLAB
   - **Option 2**: Copy the command and run it in Terminal/CMD
5. Click "Copy Command" to copy the installation command to clipboard
6. Restart the application after installation

**Benefits:**
- Automatically detects your MATLAB installation path
- Provides copy-paste ready commands with correct paths
- Works with all Python environments (including Windows Store Python)
- No complex troubleshooting needed

#### Manual Installation Instructions

**For MATLAB Engine (if automatic installation fails):**

*Option 1 - In MATLAB:*
```matlab
cd(fullfile(matlabroot,'extern','engines','python'))
system('python setup.py install')
```

*Option 2 - In Terminal/CMD:*
```bash
cd <matlabroot>/extern/engines/python
python setup.py install
```

**For MATLAB CleanLine Plugin (Gold Standard):**
```bash
# 1. Install MATLAB (license required)
# 2. Install EEGLAB from https://sccn.ucsd.edu/eeglab/download.php
# 3. In EEGLAB: File → Manage EEGLAB extensions → CleanLine
# 4. Add EEGLAB to MATLAB path (in startup.m or manually)
# 5. Install MATLAB Engine (see above or use automatic installation)
```

**For Octave (Free):**
```bash
# 1. Install Octave from https://octave.org/download
# 2. Install Python package:
pip install oct2py
```

After installing any optional dependencies, restart the application to detect them.

#### Methods Info Button
Click the **"📖 Methods Info (Detailed Comparison)"** button to open a comprehensive dialog comparing all methods with:
- Detailed technical descriptions
- Advantages and disadvantages
- Speed and quality comparisons
- Installation guides
- Technical implementation details

For more information about the Line Noise Removal step, see [Line Noise Removal](../processing/line_noise_removal.md).

### Openhdemg Installation
hdsemg-pipe can install the [openhdemg](https://www.giacomovalli.com/openhdemg/) open source project automatically from PyPI. If the application is running
from the sources, you can install openhdemg by going to Settings > Preferences > openhdemg > Install openhdemg. More information about the project can be found here: [Official Openhdemg Documentation](https://www.giacomovalli.com/openhdemg/quick-start/).

### Logging Level
The **Logging Level** section allows you to specify the logging level of the application. This is useful for debugging and troubleshooting purposes. The available logging levels are:
- `DEBUG`: Detailed information, useful for debugging.
- `INFO`: General information about application operations.
- `WARNING`: Indications of potential issues.
- `ERROR`: Error messages indicating problems that need attention.
- `CRITICAL`: Severe errors that may prevent the application from functioning.

The current logging level is displayed in the settings dialog, and you can change it by selecting a different level from the dropdown menu and pressing the "Apply" button.

> As soon as the settings dialog is closed by pressing the "OK" button, the application will save the settings to a JSON file in the application data directory. The file is named `config/config.json` and contains all the configuration options, including the working directory, external hdsemg-select path, openhdemg executable path, and logging level.