# Developer Guide for hdsemg-pipe

This guide is intended for developers who want to contribute to the hdsemg-pipe project.

## Project Structure

The project is structured as follows:

- `src/` - Main source code
  - `actions/` - Implementation of main functionalities (file management, ROI cropping, etc.)
  - `config/` - Configuration management
  - `controller/` - Control logic
  - `settings/` - Settings dialogs
  - `state/` - State management
  - `ui_elements/` - Reusable UI components
  - `widgets/` - Main widgets for different processing steps
  - `_log/` - Logging functionality

## Main Components

### Processing Steps

The application is divided into several processing steps, implemented through separate widget classes in the `widgets/` directory:

1. `OpenFileStepWidget` - File selection and import
2. `DefineRoiStepWidget` - Region of Interest (ROI) definition
3. `ChannelSelectionStepWidget` - Channel selection
4. `GridAssociationStepWidget` - Electrode grid association
5. `DecompositionStepWidget` - Signal decomposition

### State Management

Global state management is handled through the `global_state.py` module in the `state/` directory. This ensures consistency between different processing steps.

### Configuration

Application configuration is managed in the `config/` directory:
- `config_manager.py` - Management of configuration settings
- `config.json` - Persistent configuration file
- `config_enums.py` - Enumeration types for configuration options

## Development Guidelines

### Code Style

- Follow PEP 8 for Python code style
- Use meaningful variable and function names
- Document complex functions with docstrings

### Error Handling

- Implement appropriate error handling with try-except blocks
- Use the integrated logging system (`_log/` directory)
- Catch Qt-specific exceptions appropriately

### UI Development

- New UI elements should inherit from existing base classes
- Use Qt Designer for complex layouts
- Ensure new UI elements are responsive

### Testing

- Write unit tests for new functionality
- Test edge cases in signal processing
- Perform manual UI testing

## Build Process

### Dependencies

Project dependencies are defined in two files:
- `requirements.txt` - Python packages for pip
- `environment.yml` - Conda environment definition

### Resources

Qt resources are defined in `resources.qrc` and need to be recompiled after changes:
```bash
pyrcc5 resources.qrc -o resources_rc.py
```

### Versioning

Version management is handled through `make_version.py` and `version.py`.

## Documentation

- Use MkDocs for project documentation
- Document changes in the corresponding markdown file in the `docs/` directory
- Update screenshots in `docs/img/` directory when UI changes

## Contributing

1. Fork the repository
2. Create a feature branch
3. Implement your changes
4. Run tests
5. Create a pull request

## Support

For questions or issues:
- Check the existing documentation
- Create an issue in the repository
- Contact the development team

## License

Make sure your contributions comply with the project license.
