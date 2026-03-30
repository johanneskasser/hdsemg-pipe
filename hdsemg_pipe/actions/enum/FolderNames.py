from enum import Enum

class FolderNames(Enum):
    ORIGINAL_FILES = "original_files"
    CHANNELSELECTION = "channelselection"
    ASSOCIATED_GRIDS = "associated_grids"
    LINE_NOISE_CLEANED = "line_noise_cleaned"
    DECOMPOSITION_AUTO = "decomposition_auto"
    DECOMPOSITION_MUEDIT = "decomposition_muedit"
    DECOMPOSITION_REMOVED_DUPLICATES = "decomposition_removed_duplicates"
    DECOMPOSITION_COVISI_FILTERED = "decomposition_covisi_filtered"
    DECOMPOSITION_RESULTS = "decomposition_results"
    CROPPED_SIGNAL = "cropped_signal"
    ANALYSIS = "analysis"

    @classmethod
    def list_values(cls):
        return [
            cls.ASSOCIATED_GRIDS.value,
            cls.LINE_NOISE_CLEANED.value,
            cls.ANALYSIS.value,
            cls.CHANNELSELECTION.value,
            cls.DECOMPOSITION_AUTO.value,
            cls.DECOMPOSITION_MUEDIT.value,
            cls.DECOMPOSITION_REMOVED_DUPLICATES.value,
            cls.DECOMPOSITION_COVISI_FILTERED.value,
            cls.DECOMPOSITION_RESULTS.value,
            cls.CROPPED_SIGNAL.value,
            cls.ORIGINAL_FILES.value
        ]