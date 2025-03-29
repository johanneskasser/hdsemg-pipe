from PyQt5.QtCore import Qt

def update_channel_status_single(channel_status, idx, state):
    channel_status[idx] = (state == Qt.Checked)

def select_all_channels(channel_status, select):
    return [select] * len(channel_status)

def count_selected_channels(channel_status):
    return sum(channel_status)
