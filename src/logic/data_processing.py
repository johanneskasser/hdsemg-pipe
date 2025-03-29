import numpy as np
from scipy.signal import welch

def compute_upper_quartile(data):
    abs_amplitudes = np.abs(data)
    upper_quartile = np.percentile(abs_amplitudes, 75)
    return upper_quartile

def scale_data(data, upper_quartile):
    if upper_quartile == 0:
        return data
    return data / upper_quartile


# %% ---------------------------------------------------------------------------
# welchPS
# -----------------------------------------------------------------------------
#  CREDIT
#   https://stackoverflow.com/questions/57828899/prefactors-computing-psd-of-a-signal-with-numpy-fft-vs-scipy-signal-welch
def welchPS(y, fs):
    """
    Welch method FFT transform signal

    INPUT
     y   ... array of floats, n x 1; signal [unit]
     fs  ... number, n = 1; sampling frequency [Hz]

    OUTPUT
     xf  ... array of floats, n/2 x 1; frequencies [Hz]
     yf  ... array of floats, n/2 x 1; proportion of each frequency [unit**2]

    Note
     Check absoulte value of power
    """
    # TEST-CODE with peaks at 50 and 80 Hz
    """
    import numpy as np
    import matplotlib.pyplot as plt
    N = 600
    # sample spacing
    T = 1.0 / 800.0
    x = np.linspace(0.0, N*T, N)
    y = np.sin(50.0 * 2.0*np.pi*x) + 0.5*np.sin(80.0 * 2.0*np.pi*x)
    xf,yf  = doFFT(y,800)
    fig, ax = plt.subplots()
    ax.plot(xf, yf)
    plt.show()
    """
    # power spectrum, via scipy welch. 'boxcar' means no window, nperseg=len(y) so that fft computed on the whole signal.
    xf, yf = welch(y, fs=fs, window='boxcar', nperseg=len(y), scaling='spectrum', axis=-1, average='mean')
    yf = yf * 4
    return xf, yf
