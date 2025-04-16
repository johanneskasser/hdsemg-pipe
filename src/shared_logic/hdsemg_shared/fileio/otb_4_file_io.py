import logging
import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

import xml.etree.ElementTree as ET


def load_otb4_file(file_path):
    """
    Load and process an OTB4 file.

    This function handles the extraction of the OTB4 file, validates its contents,
    parses the associated XML file, and processes signal data. It returns the
    processed data, time array, descriptions, sampling frequency, file name, and
    file size.

    Args:
        file_path (str): Path to the OTB4 file to be loaded.

    Returns:
        tuple: A tuple containing:
            - data (numpy.ndarray): Processed signal data.
            - time (numpy.ndarray): Time array corresponding to the data.
            - description_array (numpy.ndarray): Array of channel descriptions.
            - sampling_frequency (float): Sampling frequency of the signals.
            - file_name (str): Name of the OTB4 file.
            - file_size (int): Size of the OTB4 file in bytes.

    Raises:
        ValueError: If the OTB4 file format is unrecognized or if no track info is found.
        FileNotFoundError: If the required XML file is missing.
        RuntimeError: If the extraction of the OTB4 file fails.
    """
    logger.debug(f"load_otb4_file called with file_path={file_path}")
    file_path_obj = Path(file_path)
    file_name = file_path_obj.name
    file_size = os.path.getsize(file_path)

    tmpdir = tempfile.mkdtemp(prefix="otb4_tmp_")
    logger.debug(f"Created temp directory: {tmpdir}")

    # Attempt to extract .otb4 (which presumably is a tar or zip)
    try:
        if tarfile.is_tarfile(file_path):
            with tarfile.open(file_path, 'r') as t:
                t.extractall(path=tmpdir)
        elif zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, 'r') as z:
                z.extractall(path=tmpdir)
        else:
            logger.warning("OTB4 file is neither recognized as tar nor zip.")
            raise ValueError("Unrecognized OTB4 archive format.")
    except Exception as exc:
        logger.error(f"Extraction failed for {file_path}: {exc}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(f"Failed to extract OTB4 file: {file_path}") from exc

    # Look for "Tracks_000.xml" - as in your .m code
    tracks_xml = os.path.join(tmpdir, "Tracks_000.xml")
    if not os.path.exists(tracks_xml):
        logger.warning(f"Missing 'Tracks_000.xml' in extracted OTB4 folder: {tmpdir}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise FileNotFoundError("No Tracks_000.xml found for OTB4 data.")

    logger.debug(f"Parsing OTB4 XML: {tracks_xml}")
    track_info_list = parse_otb4_tracks_xml(tracks_xml)  # We'll define below

    # We'll also list .sig files in tmpdir
    signals = []
    for root, dirs, files in os.walk(tmpdir):
        for f in files:
            if f.lower().endswith(".sig"):
                signals.append(os.path.join(root, f))

    logger.debug(f"Found .sig files for OTB4: {signals}")

    # Now, let's gather info from track_info_list. e.g. sum up channels, detect device type, etc.
    # The .m code references `device = textscan(...)` from the first track. We'll replicate that:
    if len(track_info_list) == 0:
        logger.error("No <TrackInfo> found in Tracks_000.xml. Can't proceed.")
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError("No track info in OTB4 xml.")
    device = track_info_list[0]["Device"]
    logger.debug(f"OTB4 device name: {device}")

    # Sum total channels from track_info
    total_channels = sum(tr["NumberOfChannels"] for tr in track_info_list)
    logger.debug(f"Total channels from tracks: {total_channels}")

    # We'll create final data array shape (total_channels x Nsamples) if we unify signals
    # Because your MATLAB code does different things depending on device = 'Novecento+' or not:
    if device == "Novecento+":
        # You appear to read multiple .sig files in a loop. We'll unify them for the final array
        # We'll store each .sig in a separate chunk
        # Then in the end, we might block them horizontally or vertically?
        # Actually in the .m code, you do "for i=2:length(signals)" ...
        # We'll do a simpler approach here for demonstration.
        data, descriptions, fs_main = read_novecento_plus(signals, track_info_list)
    else:
        # The code in else reads the first .sig with short int, merges Gains from multiple track info
        data, descriptions, fs_main = read_standard_otb4(signals, track_info_list)

    # We'll produce the final Nx1 description array
    # "descriptions" might be a list of strings, length= total_channels
    description_array = np.empty((total_channels, 1), dtype=object)
    for i, desc_str in enumerate(descriptions):
        description_array[i, 0] = desc_str

    # We guess sampling_frequency is the same for all track_info, or from the first
    sampling_frequency = fs_main

    n_samples = data.shape[1]
    time = np.arange(n_samples) / sampling_frequency

    # clean up
    shutil.rmtree(tmpdir, ignore_errors=True)
    logger.info(f"OTB4 file loaded successfully: {file_name}")

    return data, time, description_array, sampling_frequency, file_name, file_size


def parse_otb4_tracks_xml(xml_file):
    """
    Parse 'Tracks_000.xml' to gather arrayOfTrackInfo.
    We'll return a list of dict, e.g.:
      [ {
          "Device": "Novecento+",
          "Gain": ...,
          "ADC_Nbits": ...,
          "ADC_Range": ...,
          "SamplingFrequency": ...,
          "SignalStreamPath": "..."
          "NumberOfChannels": ...
          "AcquisitionChannel": ...
        }, ... ]
    """
    tree = ET.parse(xml_file)
    root = tree.getroot()

    track_info_parent = root.find("ArrayOfTrackInfo")
    if track_info_parent is None:
        return []

    # The .m code references "abs.ArrayOfTrackInfo.TrackInfo"
    # so we find <TrackInfo> children
    track_info_elems = track_info_parent.findall("TrackInfo")
    results = []
    for tr_el in track_info_elems:
        # read out the sub-elements Gains, nADBit, etc. from your .m snippet
        device_str = getattr(tr_el.find("Device"), "text", "Unknown")
        gain_str = getattr(tr_el.find("Gain"), "text", "1")
        bits_str = getattr(tr_el.find("ADC_Nbits"), "text", "16")
        rng_str = getattr(tr_el.find("ADC_Range"), "text", "5")
        fs_str = getattr(tr_el.find("SamplingFrequency"), "text", "2000")
        path_str = getattr(tr_el.find("SignalStreamPath"), "text", "")
        nchan_str = getattr(tr_el.find("NumberOfChannels"), "text", "0")
        acq_str = getattr(tr_el.find("AcquisitionChannel"), "text", "0")

        # convert
        device_str = device_str.strip()
        gain_val = float(gain_str.strip())
        bits_val = int(bits_str.strip())
        rng_val = float(rng_str.strip())
        fs_val = float(fs_str.strip())
        path_str = path_str.strip()
        nchan_val = int(nchan_str.strip())
        acq_val = int(acq_str.strip())

        results.append({
            "Device": device_str,
            "Gain": gain_val,
            "ADC_Nbits": bits_val,
            "ADC_Range": rng_val,
            "SamplingFrequency": fs_val,
            "SignalStreamPath": path_str,
            "NumberOfChannels": nchan_val,
            "AcquisitionChannel": acq_val
        })

    return results


def read_novecento_plus(signals, track_info_list):
    """
    For the 'Novecento+' device, the .m code loops multiple signals,
    tries to match Path, sets Gains, etc., and reads data as 'int32'.
    We'll unify them and return final (data, descriptions, fs).
    For demonstration, we assume each .sig is separate chunk of channels.
    """
    logger.debug("read_novecento_plus routine")
    # We'll create a big list of channel blocks
    data_blocks = []
    descriptions = []
    fs_main = None

    # The .m code does: for i=2:length(signals) ...
    # But we just do a simple approach. We'll iterate all except maybe the first if needed
    for sig_path in signals:
        # find track that references this sig file
        matched_track = None
        for tr in track_info_list:
            if tr["SignalStreamPath"] == os.path.basename(sig_path):
                matched_track = tr
                break
        if matched_track is None:
            # skip
            continue

        n_ch = matched_track["NumberOfChannels"]
        # read raw as int32
        raw = np.fromfile(sig_path, dtype=np.int32)
        samples = raw.size // n_ch
        raw = raw[:samples * n_ch]
        block = raw.reshape((n_ch, samples), order='F')

        # scale
        # data(Ch,:)=data(Ch,:)*Psup/(2^ADbit)*1000/Gain
        conv = matched_track["ADC_Range"] / (2 ** matched_track["ADC_Nbits"]) * 1000 / matched_track["Gain"]
        block = block.astype(np.float64) * conv

        data_blocks.append(block)

        # keep track of fs
        if fs_main is None:
            fs_main = matched_track["SamplingFrequency"]
        else:
            # if you want to check consistency:
            if abs(fs_main - matched_track["SamplingFrequency"]) > 1e-9:
                logger.warning("Inconsistent sampling freq among tracks?")

        # build placeholder descriptions:
        # e.g. "Novecento+ <SignalStreamPath> channel x"
        # TODO: We have to adjust channels once XML Structure is cleared!
        for c in range(n_ch):
            desc = f"{matched_track['Device']}-{matched_track['SignalStreamPath']}-ch{c}"
            descriptions.append(desc)

    # now we might stack these blocks vertically so shape= totalCh x samples
    # But if blocks differ in samples => need to unify or so. We'll do a minimal approach:
    # check all same number of samples? If so, vstack:
    lens = [b.shape[1] for b in data_blocks]
    if not all(l == lens[0] for l in lens):
        # mismatch sample counts => handle or raise
        logger.warning("Different sample lengths among signals. We'll pick min length.")
        min_len = min(lens)
        for i in range(len(data_blocks)):
            data_blocks[i] = data_blocks[i][:, :min_len]

    # vstack them
    final_data = np.vstack(data_blocks) if data_blocks else np.zeros((0, 0))
    return final_data, descriptions, fs_main or 2000


def read_standard_otb4(signals, track_info_list):
    """
    For the else case in the .m code:
    We read the *first* .sig using 'short' if so indicated,
    then apply Gains for each track in partial channel intervals.
    """
    logger.debug("read_standard_otb4 routine")

    if not signals:
        return np.zeros((0, 0)), [], 2000.0

    sig_path = signals[0]  # the .m code uses the first .sig
    # sum up totalCh
    totalCh = sum(tr["NumberOfChannels"] for tr in track_info_list)
    # read 'short' => int16
    raw = np.fromfile(sig_path, dtype=np.int16)
    samples = raw.size // totalCh
    raw = raw[:samples * totalCh]
    data_2d = raw.reshape((totalCh, samples), order='F').astype(np.float64)

    # parse track_info: we do the "for i=2:... in matlab, but basically we do the Gains scaling
    # The code in .m says for nSig=1 => we do data= short => then we have sumidx / idx array, etc.

    # We'll create an array of indexes:
    indexes = []
    running_sum = 0
    for tr in track_info_list:
        running_sum += tr["NumberOfChannels"]
        indexes.append(running_sum)
    # e.g. if track1 has 32 channels => idx=32, track2 => idx=64, etc

    # now apply Gains scaling for each block
    # in .m: data(nCh,:) = data(nCh,:) * PowerSupply{ntype} / (2^nADBit{ntype}) * 1000 / Gains{ntype}
    # We'll store partial indexing in ascending order
    start_idx = 0
    for i, trackinfo in enumerate(track_info_list):
        end_idx = indexes[i]
        psup = trackinfo["ADC_Range"]
        nbits = trackinfo["ADC_Nbits"]
        gainv = trackinfo["Gain"]
        conv = psup / (2 ** nbits) * 1000.0 / gainv
        for ch in range(start_idx, end_idx):
            data_2d[ch, :] *= conv
        start_idx = end_idx

    # build description strings
    descriptions = []
    start_idx = 0
    for tr in track_info_list:
        dev = tr["Device"]
        path = tr["SignalStreamPath"]
        nchan = tr["NumberOfChannels"]
        for c in range(nchan):
            desc = f"{dev}-{path}-ch{c}"
            descriptions.append(desc)
        start_idx += nchan

    # the .m code picks the sample freq from e.g. Fsample{nSig}, presumably from the first track
    fs_main = track_info_list[0]["SamplingFrequency"] if track_info_list else 2000.0

    return data_2d, descriptions, fs_main
