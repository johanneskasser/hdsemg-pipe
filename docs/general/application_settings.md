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