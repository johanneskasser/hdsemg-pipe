import sys
import os
from PyQt5.QtGui import QIcon, QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QAction,
    qApp, QStackedWidget, QPushButton, QHBoxLayout, QStyleFactory
)
from PyQt5.QtCore import Qt
from hdsemg_pipe.ui_elements.theme import get_app_stylesheet

from hdsemg_pipe._log.exception_hook import exception_hook
from hdsemg_pipe.controller.automatic_state_reconstruction import start_reconstruction_workflow
from hdsemg_pipe.settings.settings_dialog import SettingsDialog
from hdsemg_pipe._log.log_config import logger, setup_logging
from hdsemg_pipe.state.global_state import global_state
from hdsemg_pipe.version import __version__

# Import new wizard components
from hdsemg_pipe.widgets.StepProgressIndicator import StepProgressIndicator
from hdsemg_pipe.widgets.NavigationFooter import NavigationFooter
from hdsemg_pipe.widgets.FolderContentDrawer import FolderContentDrawer

# Import all wizard widgets
from hdsemg_pipe.widgets.wizard.OpenFileWizardWidget import OpenFileWizardWidget
from hdsemg_pipe.widgets.wizard.GridAssociationWizardWidget import GridAssociationWizardWidget
from hdsemg_pipe.widgets.wizard.LineNoiseRemovalWizardWidget import LineNoiseRemovalWizardWidget
from hdsemg_pipe.widgets.wizard.RMSQualityWizardWidget import RMSQualityWizardWidget
from hdsemg_pipe.widgets.wizard.DefineRoiWizardWidget import DefineRoiWizardWidget
from hdsemg_pipe.widgets.wizard.ChannelSelectionWizardWidget import ChannelSelectionWizardWidget
from hdsemg_pipe.widgets.wizard.DecompositionResultsWizardWidget import DecompositionResultsWizardWidget
from hdsemg_pipe.widgets.wizard.MultiGridConfigWizardWidget import MultiGridConfigWizardWidget
from hdsemg_pipe.widgets.wizard.CoVISIPreFilterWizardWidget import CoVISIPreFilterWizardWidget
from hdsemg_pipe.widgets.wizard.MUEditCleaningWizardWidget import MUEditCleaningWizardWidget
from hdsemg_pipe.widgets.wizard.CoVISIPostValidationWizardWidget import CoVISIPostValidationWizardWidget
from hdsemg_pipe.widgets.wizard.FinalResultsWizardWidget import FinalResultsWizardWidget

from hdsemg_pipe.ui_elements.theme import Colors, Styles
from hdsemg_pipe.ui_elements.toast import toast_manager

import hdsemg_pipe.resources_rc


class WizardMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.folder_drawer = None
        self.steps = []
        self.current_step_index = 0
        self.settingsDialog = SettingsDialog(self)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("hdsemg-pipe")
        self.setWindowIcon(QIcon(":/resources/icon.png"))
        self.setGeometry(100, 100, 1000, 700)

        # Menu Bar
        menubar = self.menuBar()
        settings_menu = menubar.addMenu('Settings')

        preferences_action = QAction('Preferences', self)
        preferences_action.triggered.connect(self.openPreferences)
        settings_menu.addAction(preferences_action)

        open_existing_workfolder_action = QAction('Open Existing Workfolder', self)
        open_existing_workfolder_action.triggered.connect(self.openExistingWorkfolder)
        settings_menu.addAction(open_existing_workfolder_action)

        settings_menu.addSeparator()

        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(qApp.quit)
        settings_menu.addAction(exit_action)

        # Central Widget with Wizard Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top: Step Progress Indicator
        self.progress_indicator = StepProgressIndicator()
        self.progress_indicator.stepClicked.connect(self.navigateToStep)
        main_layout.addWidget(self.progress_indicator)

        # Middle: Content area with drawer toggle button
        content_container = QWidget()
        content_layout = QHBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Stacked Widget for Steps
        self.step_stack = QStackedWidget()
        content_layout.addWidget(self.step_stack, stretch=1)

        main_layout.addWidget(content_container, stretch=1)

        # Bottom: Navigation Footer
        self.nav_footer = NavigationFooter()
        self.nav_footer.previousClicked.connect(self.navigatePrevious)
        self.nav_footer.nextClicked.connect(self.navigateNext)
        main_layout.addWidget(self.nav_footer)

        # Create Folder Drawer
        self.folder_drawer = FolderContentDrawer(central_widget)
        self.folder_drawer.drawerToggled.connect(self.onDrawerToggled)
        global_state.register_widget(name="folder_content", widget=self.folder_drawer.folder_content)

        # Initialize toast manager
        toast_manager.set_parent(central_widget)

        # Initialize all wizard-style steps
        self.initSteps()

        # Set up step connections
        self.connectSteps()

        # Status Bar
        self.statusBar().showMessage(f"hdsemg-pipe v{__version__} | University of Applied Sciences Campus Wien")

        # Update navigation buttons
        self.updateNavigation()

    def initSteps(self):
        """Initialize all step widgets."""
        # Step 1: Open File(s)
        step1 = OpenFileWizardWidget()
        global_state.register_widget(step1, name="step1")
        self.steps.append(step1)
        self.step_stack.addWidget(step1)
        step1.check()

        # Step 2: Grid Association
        step2 = GridAssociationWizardWidget()
        global_state.register_widget(step2, name="step2")
        self.steps.append(step2)
        self.step_stack.addWidget(step2)
        step2.check()

        # Step 3: Line Noise Removal
        step3 = LineNoiseRemovalWizardWidget()
        global_state.register_widget(step3, name="step3")
        self.steps.append(step3)
        self.step_stack.addWidget(step3)
        step3.check()

        # Step 4: RMS Quality Analysis
        step4 = RMSQualityWizardWidget()
        global_state.register_widget(step4, name="step4")
        self.steps.append(step4)
        self.step_stack.addWidget(step4)
        step4.check()

        # Step 5: Define ROI
        step5 = DefineRoiWizardWidget()
        global_state.register_widget(step5, name="step5")
        self.steps.append(step5)
        self.step_stack.addWidget(step5)
        step5.check()

        # Step 6: Channel Selection
        step6 = ChannelSelectionWizardWidget()
        global_state.register_widget(step6, name="step6")
        self.steps.append(step6)
        self.step_stack.addWidget(step6)
        step6.check()

        # Step 7: Decomposition Results
        step7 = DecompositionResultsWizardWidget()
        global_state.register_widget(step7, name="step7")
        self.steps.append(step7)
        self.step_stack.addWidget(step7)
        step7.check()

        # Step 8: Multi-Grid Configuration
        step8 = MultiGridConfigWizardWidget()
        global_state.register_widget(step8, name="step8")
        self.steps.append(step8)
        self.step_stack.addWidget(step8)
        step8.check()

        # Step 9: CoVISI Pre-Filtering (optional)
        step9 = CoVISIPreFilterWizardWidget()
        global_state.register_widget(step9, name="step9")
        self.steps.append(step9)
        self.step_stack.addWidget(step9)
        step9.check()

        # Step 10: MUEdit Manual Cleaning
        step10 = MUEditCleaningWizardWidget()
        global_state.register_widget(step10, name="step10")
        self.steps.append(step10)
        self.step_stack.addWidget(step10)
        step10.check()

        # Step 11: CoVISI Post-Validation
        step11 = CoVISIPostValidationWizardWidget()
        global_state.register_widget(step11, name="step11")
        self.steps.append(step11)
        self.step_stack.addWidget(step11)
        step11.check()

        # Step 12: Final Results
        step12 = FinalResultsWizardWidget()
        global_state.register_widget(step12, name="step12")
        self.steps.append(step12)
        self.step_stack.addWidget(step12)
        step12.check()

    def connectSteps(self):
        """Connect step signals."""
        self.settingsDialog.settingsAccepted.connect(self.checkAllSteps)

        # Connect step completion signals
        for i, step in enumerate(self.steps):
            step.stepCompleted.connect(self.onStepCompleted)

            # Connect to folder drawer update
            if hasattr(step, 'fileSelected'):
                step.fileSelected.connect(self.folder_drawer.folder_content.update_folder_content)
            step.stepCompleted.connect(self.folder_drawer.folder_content.update_folder_content)

    def onStepCompleted(self, step_index):
        """Handle step completion."""
        logger.info(f"Step {step_index} completed")

        # Update progress indicator
        self.progress_indicator.setStepState(step_index, "completed")

        # Auto-navigate to next step if not on last step
        if step_index < 12:
            self.navigateNext()

        # Check next step
        if step_index < len(self.steps):
            self.steps[step_index].check()

        self.updateNavigation()

    def navigateToStep(self, step_index):
        """Navigate to a specific step (1-indexed)."""
        if 1 <= step_index <= 12:
            self.current_step_index = step_index - 1
            self.step_stack.setCurrentIndex(self.current_step_index)
            self.progress_indicator.setActiveStep(step_index)
            self.updateNavigation()
            logger.debug(f"Navigated to step {step_index}")

    def navigatePrevious(self):
        """Navigate to previous step."""
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self.step_stack.setCurrentIndex(self.current_step_index)
            self.progress_indicator.setActiveStep(self.current_step_index + 1)
            self.updateNavigation()

    def navigateNext(self):
        """Navigate to next step."""
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
            self.step_stack.setCurrentIndex(self.current_step_index)
            self.progress_indicator.setActiveStep(self.current_step_index + 1)
            self.updateNavigation()

    def updateNavigation(self):
        """Update navigation button states."""
        # Previous button: enabled if not on first step
        self.nav_footer.setPreviousEnabled(self.current_step_index > 0)

        # Next button: enabled if not on last step
        if self.current_step_index < len(self.steps) - 1:
            self.nav_footer.setNextEnabled(True)
            self.nav_footer.setNextText("Next →")
        else:
            self.nav_footer.setNextEnabled(False)
            self.nav_footer.setNextText("Complete")

    def toggleFolderDrawer(self):
        """Toggle folder content drawer."""
        self.folder_drawer.toggle()

    def onDrawerToggled(self, is_open):
        """Handle drawer toggle event."""
        logger.debug(f"Drawer {'opened' if is_open else 'closed'}")

    def checkAllSteps(self):
        """Re-check all steps (e.g., after settings change)."""
        for step in self.steps:
            step.check()

    def openPreferences(self):
        """Open the settings dialog."""
        if self.settingsDialog.exec_():
            logger.debug("Settings dialog closed and accepted")
            self.checkAllSteps()
        else:
            logger.debug("Settings dialog closed")

    def openExistingWorkfolder(self):
        """Open existing workfolder and navigate to last completed step."""
        last_step = start_reconstruction_workflow(self)
        if last_step is not None:
            # Navigate to next step after last completed (or stay on last if all complete)
            next_step = min(last_step + 1, 11)  # 11 is last step (0-indexed)
            self.navigateToStep(next_step + 1)  # navigateToStep is 1-indexed
            logger.info(f"Navigated to step {next_step + 1} after state reconstruction")

    def resizeEvent(self, event):
        """Handle window resize to update drawer position."""
        super().resizeEvent(event)
        if self.folder_drawer:
            self.folder_drawer.updatePosition()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key_Left:
            self.navigatePrevious()
        elif event.key() == Qt.Key_Right:
            self.navigateNext()
        elif event.key() == Qt.Key_F:
            if event.modifiers() == Qt.ControlModifier:
                self.toggleFolderDrawer()
        else:
            super().keyPressEvent(event)


def main():
    # Force light mode on macOS 
    # This prevents the system's dark mode from interfering with the app's custom theme.
    if sys.platform == 'darwin':
        os.environ['QT_MAC_WANTS_LIGHT_THEME'] = '1'


    app = QApplication(sys.argv)
    
    setup_logging()
    sys.excepthook = exception_hook
    
    window = WizardMainWindow()
    window.showMaximized()  # Show the window maximized
    app.setStyleSheet(get_app_stylesheet())
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
