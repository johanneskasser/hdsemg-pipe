from matplotlib.figure import Figure

def create_channel_figure(time, data_channel, channel_idx, ylim):
    figure = Figure(figsize=(2, 1))
    ax = figure.add_subplot(111)
    ax.plot(time, data_channel, label=f"Channel {channel_idx + 1}")
    ax.set_ylim(ylim)
    ax.set_xticks([])
    ax.set_yticks([])
    return figure
