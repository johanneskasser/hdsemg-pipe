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


def load_otb_file(file_path):
    """
    Loads data from a single .otb (or .otb+ / .zip / .tar) archive and returns
    (data, time, description, sampling_frequency, file_name, file_size).
    """
    logger.debug(f"load_otb_file called with file_path={file_path}")
    file_path_obj = Path(file_path)
    file_name = file_path_obj.name
    file_size = os.path.getsize(file_path)
    logger.debug(f"File info: name={file_name}, size={file_size} bytes")

    tmpdir = tempfile.mkdtemp(prefix="otb_tmp_")
    logger.debug(f"Created temp directory: {tmpdir}")

    # Try extracting
    try:
        if tarfile.is_tarfile(file_path):
            logger.debug("File appears to be a TAR archive")
            with tarfile.open(file_path, 'r') as t:
                t.extractall(path=tmpdir)
        elif zipfile.is_zipfile(file_path):
            logger.debug("File appears to be a ZIP archive")
            with zipfile.ZipFile(file_path, 'r') as z:
                z.extractall(path=tmpdir)
        else:
            logger.warning("File is neither recognized as tar nor zip. Possibly custom format.")
            raise ValueError("The file does not appear to be tar or zip. Check OTB format.")
    except Exception as exc:
        logger.error(f"Extraction failed for {file_path}: {exc}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(f"Failed to extract {file_path}: {exc}")

    # search for .sig
    found_sig = []
    for root, dirs, files in os.walk(tmpdir):
        for fname in files:
            if fname.lower().endswith(".sig"):
                fullp = os.path.join(root, fname)
                found_sig.append(fullp)
    logger.debug(f"Found .sig files: {found_sig}")

    if not found_sig:
        logger.warning("No .sig files found after extracting.")
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise FileNotFoundError("No .sig files found in the extracted OTB archive.")

    sig_file = found_sig[0]
    logger.debug(f"Using first .sig file: {sig_file}")

    xml_file = sig_file[:-4] + ".xml"
    if not os.path.exists(xml_file):
        logger.warning(f"Expected XML not found: {xml_file}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise FileNotFoundError(f"Could not find the matching XML for {sig_file}")

    logger.debug(f"Parsing XML: {xml_file}")
    info_dict = parse_otb_xml(xml_file)

    n_channels = len(info_dict["Gains"]) if info_dict["Gains"] else 1
    nADbits = info_dict["ADbits"]
    raw_data = load_sig_data(sig_file, n_channels, nADbits)
    logger.debug(f"Loaded .sig data shape={raw_data.shape}")

    data_scaled = scale_otb_data(raw_data, info_dict["Gains"], nADbits, info_dict["DeviceName"])
    sampling_frequency = info_dict["SampleFrequency"]
    n_samples = data_scaled.shape[1]

    time = np.arange(n_samples) / sampling_frequency

    # descriptions
    description = info_dict['ChannelDescriptions']

    logger.debug(f"Cleaning up temp directory {tmpdir}")
    shutil.rmtree(tmpdir, ignore_errors=True)
    logger.info(f"OTB file loaded successfully: {file_name}")

    return data_scaled, time, description, sampling_frequency, file_name, file_size


import xml.etree.ElementTree as ET


def parse_otb_xml(xml_file):
    """
    Parse .otb XML and create a Gains array plus a ChannelDescriptions list,
    each of length 'DeviceTotalChannels'. Now includes adapter-based info
    in the channel description string.

    Returns a dict:
      {
        "DeviceName": str,
        "SampleFrequency": float,
        "ADbits": int,
        "TotalChannels": int,
        "Gains": list(float),
        "ChannelDescriptions": list(str)
      }
    """
    tree = ET.parse(xml_file)
    root = tree.getroot()

    device_name = root.attrib.get("Name", "UnknownDevice")
    fs_str = root.attrib.get("SampleFrequency", "2000")
    adbits_str = root.attrib.get("ad_bits", "16")
    total_ch_str = root.attrib.get("DeviceTotalChannels", "0")

    try:
        total_ch = int(total_ch_str)
    except ValueError:
        total_ch = 0
    if total_ch <= 0:
        total_ch = 128  # fallback

    Gains = [1.0] * total_ch
    description_map = [None] * total_ch

    # Now parse each <Adapter> in <Channels>
    channels_el = root.find('Channels')
    if channels_el is not None:
        adapters_list = channels_el.findall('Adapter')
        for adapterEl in adapters_list:
            # read adapter-level gain
            adapter_gain_str = adapterEl.attrib.get("Gain", "1")
            adapter_gain = float(adapter_gain_str)

            # read adapter-level start index
            start_index_str = adapterEl.attrib.get("ChannelStartIndex", "0")
            start_index = int(start_index_str)

            # Also fetch additional attributes at the adapter level
            adapter_id = adapterEl.attrib.get("ID", "")
            adapter_desc = adapterEl.attrib.get("Description", "")

            # find <Channel> children
            channel_els = adapterEl.findall("Channel")
            for ch_el in channel_els:
                ch_gain_str = ch_el.attrib.get("Gain", "1")
                ch_gain = float(ch_gain_str)
                ch_index = int(ch_el.attrib.get("Index", "0"))

                # Additional channel-level attributes
                cid = ch_el.attrib.get("ID", "")
                prefix = ch_el.attrib.get("Prefix", "")
                descr = ch_el.attrib.get("Description", "")
                muscle = ch_el.attrib.get("Muscle", "")
                side = ch_el.attrib.get("Side", "")

                # Now combine adapter info + channel info
                # e.g. "Adapter(Muovi-32 channels device) :Ch(HD10MM0804-MUOVI 1 - -32 Adhesive Array 10 mm i.e.d.-Vastus Medialis-Left)"
                # Or simpler: f"{adapter_id}-{adapter_desc}-{cid}-{prefix}-{descr}-{muscle}-{side}"
                ch_description = build_channel_description(
                    adapter_id, adapter_desc, cid, prefix, descr, muscle, side
                )

                abs_ch = start_index + ch_index
                Gains[abs_ch] = adapter_gain * ch_gain
                description_map[abs_ch] = ch_description

    info = {
        "DeviceName": device_name,
        "SampleFrequency": float(fs_str),
        "ADbits": int(adbits_str),
        "TotalChannels": total_ch,
        "Gains": Gains,
        "ChannelDescriptions": description_map
    }
    return info


def build_channel_description(adapter_id, adapter_desc, cid, prefix, descr, muscle, side):
    """
    Combine attributes for a channel description, skipping empty or placeholders like 'Not defined'.
    """
    fields = [adapter_id, adapter_desc, cid, prefix, descr, muscle, side]
    # Filter out empty strings or 'Not defined'
    filtered_fields = []
    for val in fields:
        if val and val.lower() != "not defined":
            # Also strip leading/trailing spaces
            v = val.strip()
            if v:
                filtered_fields.append(v)
    # Join using dashes
    return "-".join(filtered_fields)


def load_sig_data(sig_file, n_channels, nADbits=16):
    logger.debug(f"load_sig_data: file={sig_file}, n_channels={n_channels}, nADbits={nADbits}")
    if nADbits == 16:
        dtype = np.int16
    else:
        dtype = np.int32
    raw = np.fromfile(sig_file, dtype=dtype)
    n_total = raw.size
    if n_channels == 0:
        logger.warning("n_channels=0, forcing 1 to avoid ZeroDivisionError.")
        n_channels = 1
    n_per_ch = n_total // n_channels
    if n_per_ch * n_channels != n_total:
        logger.warning(f"Size mismatch: total={n_total}, leftover={n_total - (n_per_ch * n_channels)}")
    raw = raw[: n_per_ch * n_channels]  # just to align
    data_2d = raw.reshape((n_channels, n_per_ch), order='F')
    logger.debug(f"Reshaped raw data to {data_2d.shape}")
    return data_2d


def scale_otb_data(data, gains, nADbits, device_name=""):
    logger.debug(f"scale_otb_data: device={device_name}, nADbits={nADbits}, #channels={data.shape[0]}")
    if "QUATTRO" in device_name.upper():
        power_supply = 5.0
    elif "DUE" in device_name.upper():
        power_supply = 3.3
    else:
        power_supply = 5.0
    conv = power_supply / (2 ** nADbits) * 1000.0
    for i in range(data.shape[0]):
        g = gains[i] if (i < len(gains)) else 1.0
        data[i, :] = data[i, :] * (conv / g)
    logger.debug("Scaling done.")
    return data
