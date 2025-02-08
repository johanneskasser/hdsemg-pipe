# state/global_state.py
class GlobalState:
    _instance = None  # Singleton instance

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
            cls._instance.reset()  # Initialize state variables
        return cls._instance

    def reset(self):
        """Reset state variables to initial values."""
        self.mat_files = []

# Access the singleton instance anywhere in the application
global_state = GlobalState()
