from enum import Enum

class FolderNames(Enum):
    ORIGINAL_FILES = "original_files"
    CHANNELSELECTION = "channelselection"
    ASSOCIATED_GRIDS = "associated_grids"
    DECOMPOSITION = "decomposition"
    CROPPED_SIGNAL = "cropped_signal"

    @classmethod
    def list_values(cls):
        return [
            cls.ASSOCIATED_GRIDS.value,
            cls.CHANNELSELECTION.value,
            cls.DECOMPOSITION.value,
            cls.CROPPED_SIGNAL.value,
            cls.ORIGINAL_FILES.value
        ]