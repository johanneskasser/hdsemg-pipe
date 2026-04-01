from enum import Enum


class FolderNames(Enum):
    ORIGINAL_FILES = "00_original_files"
    ASSOCIATED_GRIDS = "01_associated_grids"
    LINE_NOISE_CLEANED = "02_line_noise_cleaned"
    CROPPED_SIGNAL = "03_cropped_signal"
    CHANNELSELECTION = "04_channelselection"
    DECOMPOSITION_AUTO = "05_decomposition_auto"
    DECOMPOSITION_COVISI_FILTERED = "05.1_decomposition_covisi_filtered"
    DECOMPOSITION_REMOVED_DUPLICATES = "05.2_decomposition_removed_duplicates"
    DECOMPOSITION_MUEDIT = "05.3_decomposition_muedit"
    DECOMPOSITION_SCD_EDITION = "05.3_decomposition_scd_edition"
    DECOMPOSITION_RESULTS = "06_decomposition_results"
    ANALYSIS = "07_analysis"

    @classmethod
    def list_values(cls):
        return [
            cls.ORIGINAL_FILES.value,
            cls.ASSOCIATED_GRIDS.value,
            cls.LINE_NOISE_CLEANED.value,
            cls.CROPPED_SIGNAL.value,
            cls.CHANNELSELECTION.value,
            cls.DECOMPOSITION_AUTO.value,
            cls.DECOMPOSITION_COVISI_FILTERED.value,
            cls.DECOMPOSITION_REMOVED_DUPLICATES.value,
            cls.DECOMPOSITION_MUEDIT.value,
            cls.DECOMPOSITION_SCD_EDITION.value,
            cls.DECOMPOSITION_RESULTS.value,
            cls.ANALYSIS.value,
        ]


# Migration mapping: old (un-numbered) name → new (numbered) name.
# Used by automatic_state_reconstruction to upgrade existing workfolders in-place.
FOLDER_NAME_MIGRATIONS = {
    "original_files": FolderNames.ORIGINAL_FILES.value,
    "associated_grids": FolderNames.ASSOCIATED_GRIDS.value,
    "line_noise_cleaned": FolderNames.LINE_NOISE_CLEANED.value,
    "cropped_signal": FolderNames.CROPPED_SIGNAL.value,
    "channelselection": FolderNames.CHANNELSELECTION.value,
    "decomposition_auto": FolderNames.DECOMPOSITION_AUTO.value,
    "decomposition_covisi_filtered": FolderNames.DECOMPOSITION_COVISI_FILTERED.value,
    "decomposition_removed_duplicates": FolderNames.DECOMPOSITION_REMOVED_DUPLICATES.value,
    "decomposition_muedit": FolderNames.DECOMPOSITION_MUEDIT.value,
    "decomposition_results": FolderNames.DECOMPOSITION_RESULTS.value,
    "analysis": FolderNames.ANALYSIS.value,
}
