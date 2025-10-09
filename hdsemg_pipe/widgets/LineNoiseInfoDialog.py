"""
Information dialog explaining different line noise removal methods.
"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt


class LineNoiseInfoDialog(QDialog):
    """Dialog displaying detailed information about line noise removal methods."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Line Noise Removal Methods - Information")
        self.setMinimumSize(850, 700)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # Text browser for rich text display
        info_text = QTextBrowser()
        info_text.setOpenExternalLinks(True)
        info_text.setHtml(self.get_info_html())
        layout.addWidget(info_text)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

    def get_info_html(self):
        """Returns HTML-formatted information about line noise removal methods."""
        return """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 10px; }
                h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }
                h2 { color: #34495e; margin-top: 20px; }
                h3 { color: #7f8c8d; }
                .method {
                    background-color: #ecf0f1;
                    padding: 10px;
                    margin: 10px 0;
                    border-left: 4px solid #3498db;
                }
                .pro { color: #27ae60; font-weight: bold; }
                .con { color: #e74c3c; font-weight: bold; }
                .note {
                    background-color: #fff3cd;
                    padding: 10px;
                    border-left: 4px solid #ffc107;
                    margin: 10px 0;
                }
                table {
                    border-collapse: collapse;
                    width: 100%;
                    margin: 15px 0;
                }
                th, td {
                    border: 1px solid #bdc3c7;
                    padding: 8px;
                    text-align: left;
                }
                th {
                    background-color: #3498db;
                    color: white;
                }
                tr:nth-child(even) {
                    background-color: #f2f2f2;
                }
            </style>
        </head>
        <body>
            <h1>Line Noise Removal for HD-sEMG Signals</h1>

            <p>Powerline noise (50 Hz in Europe, 60 Hz in North America) and its harmonics are common
            artifacts in electrophysiological recordings. This step removes these sinusoidal
            interference components from your HD-sEMG data.</p>

            <h2>Available Methods</h2>

            <div class="method">
                <h3>1. MNE-Python: Notch Filter (FIR)</h3>
                <p><strong>Type:</strong> Finite Impulse Response (FIR) filter</p>
                <p><strong>Description:</strong> Creates narrow rejection bands at specified frequencies
                using a FIR filter design. This is the classic "notch filter" approach.</p>

                <p class="pro">✓ Advantages:</p>
                <ul>
                    <li>Very fast and efficient</li>
                    <li>Stable filtering (no phase shift with zero-phase)</li>
                    <li>Simple to understand and predictable</li>
                    <li>No external dependencies (only MNE-Python)</li>
                </ul>

                <p class="con">✗ Disadvantages:</p>
                <ul>
                    <li>Also removes frequencies near the target frequency ("frequency hole")</li>
                    <li>Can cause distortions in time domain</li>
                    <li>Not adaptive - uses fixed frequencies</li>
                    <li>Can be problematic for narrowband signals</li>
                </ul>

                <p><strong>Recommended for:</strong> Fast processing when slight spectral distortions are acceptable.</p>
            </div>

            <div class="method">
                <h3>2. MNE-Python: Spectrum Fit (Adaptive)</h3>
                <p><strong>Type:</strong> Spectrum fitting with sinusoidal regression</p>
                <p><strong>Description:</strong> Adaptively estimates and removes sinusoidal components
                using sliding windows. Similar approach to CleanLine used in EEGLAB.</p>

                <p class="pro">✓ Advantages:</p>
                <ul>
                    <li>Adaptive - adjusts to time-varying interference</li>
                    <li>Minimal distortion of adjacent frequencies</li>
                    <li>Narrower removal than classical notch filters</li>
                    <li>No external dependencies (only MNE-Python)</li>
                    <li>Similar approach to CleanLine (multi-taper method)</li>
                </ul>

                <p class="con">✗ Disadvantages:</p>
                <ul>
                    <li>Slower than simple notch filter</li>
                    <li>More computationally intensive for long signals</li>
                    <li>More parameters to tune</li>
                </ul>

                <p><strong>Recommended for:</strong> High-quality signal processing with minimal
                distortion when processing time is not critical.</p>
            </div>

            <div class="method">
                <h3>3. MATLAB CleanLine (EEGLAB Plugin)</h3>
                <p><strong>Type:</strong> Adaptive multi-taper regression with Thompson F-statistic</p>
                <p><strong>Description:</strong> The original CleanLine algorithm from EEGLAB. Uses
                multi-taper spectral analysis in sliding windows to adaptively estimate and remove
                line noise with statistical validation.</p>

                <p class="pro">✓ Advantages:</p>
                <ul>
                    <li><strong>Gold standard</strong> for adaptive line noise removal</li>
                    <li>Statistical validation using Thompson F-test</li>
                    <li>Excellent for time-varying line noise</li>
                    <li>Well-tested in neuroscience community</li>
                    <li>Can automatically detect line noise frequencies</li>
                </ul>

                <p class="con">✗ Disadvantages:</p>
                <ul>
                    <li><strong>Requires MATLAB license</strong> (commercial)</li>
                    <li>Requires CleanLine plugin installation</li>
                    <li>Slower due to Python-MATLAB communication</li>
                    <li>Most computationally intensive method</li>
                    <li>Higher memory usage</li>
                </ul>

                <p><strong>Recommended for:</strong> Users with MATLAB + EEGLAB setup who need
                the highest quality adaptive filtering and are familiar with CleanLine parameters.</p>
            </div>

            <div class="method">
                <h3>4. MATLAB: IIR Notch Filter</h3>
                <p><strong>Type:</strong> Infinite Impulse Response (IIR) notch filter</p>
                <p><strong>Description:</strong> Uses MATLAB's <code>iirnotch</code> and
                <code>filtfilt</code> functions to create and apply notch filters.</p>

                <p class="pro">✓ Advantages:</p>
                <ul>
                    <li>Native MATLAB implementation</li>
                    <li>Very narrow-band filtering possible</li>
                    <li>Well documented and established</li>
                    <li>Compatible with existing MATLAB workflows</li>
                </ul>

                <p class="con">✗ Disadvantages:</p>
                <ul>
                    <li><strong>Requires MATLAB license</strong> (commercial)</li>
                    <li>MATLAB Engine for Python must be installed</li>
                    <li>Slower due to Python-MATLAB communication</li>
                    <li>Higher memory usage from data conversion</li>
                </ul>

                <p><strong>Recommended for:</strong> Users with existing MATLAB license who
                prefer MATLAB-native implementations.</p>
            </div>

            <div class="method">
                <h3>5. Octave: IIR Notch Filter (Free)</h3>
                <p><strong>Type:</strong> Infinite Impulse Response (IIR) notch filter via Octave</p>
                <p><strong>Description:</strong> Uses GNU Octave (MATLAB-compatible) via oct2py
                to apply notch filters.</p>

                <p class="pro">✓ Advantages:</p>
                <ul>
                    <li><strong>Free and Open Source</strong></li>
                    <li>MATLAB-compatible syntax</li>
                    <li>Similar results to MATLAB</li>
                    <li>No license costs</li>
                </ul>

                <p class="con">✗ Disadvantages:</p>
                <ul>
                    <li>Octave and oct2py must be installed separately</li>
                    <li>Slower due to Python-Octave communication</li>
                    <li>~95% MATLAB compatible (minor differences possible)</li>
                    <li>Additional software dependency</li>
                </ul>

                <p><strong>Recommended for:</strong> Users without MATLAB license who want
                MATLAB-like processing.</p>
            </div>

            <h2>Comparison Table</h2>
            <table>
                <tr>
                    <th>Method</th>
                    <th>Speed</th>
                    <th>Quality</th>
                    <th>Cost</th>
                    <th>Installation</th>
                </tr>
                <tr>
                    <td>MNE Notch Filter</td>
                    <td>⚡⚡⚡ Very fast</td>
                    <td>⭐⭐⭐ Good</td>
                    <td>Free</td>
                    <td>pip install mne</td>
                </tr>
                <tr>
                    <td>MNE Spectrum Fit</td>
                    <td>⚡⚡ Medium</td>
                    <td>⭐⭐⭐⭐⭐ Excellent</td>
                    <td>Free</td>
                    <td>pip install mne</td>
                </tr>
                <tr>
                    <td>MATLAB CleanLine</td>
                    <td>⚡ Slow</td>
                    <td>⭐⭐⭐⭐⭐ Excellent (Gold std.)</td>
                    <td>MATLAB license required</td>
                    <td>MATLAB + EEGLAB + CleanLine</td>
                </tr>
                <tr>
                    <td>MATLAB IIR</td>
                    <td>⚡⚡ Medium</td>
                    <td>⭐⭐⭐⭐ Very good</td>
                    <td>MATLAB license required</td>
                    <td>MATLAB + Engine API</td>
                </tr>
                <tr>
                    <td>Octave IIR</td>
                    <td>⚡ Slow</td>
                    <td>⭐⭐⭐⭐ Very good</td>
                    <td>Free</td>
                    <td>Octave + oct2py</td>
                </tr>
            </table>

            <div class="note">
                <strong>💡 Recommendation:</strong> For most use cases,
                <strong>MNE Spectrum Fit</strong> is the best choice. It offers excellent quality,
                is free, and requires no additional software besides MNE-Python. If you have MATLAB
                and need the absolute best adaptive filtering, <strong>CleanLine</strong> is the gold standard.
            </div>

            <h2>Technical Details: Notch Filter</h2>

            <p>A <strong>Notch Filter</strong> is a band-stop filter that suppresses a very narrow
            frequency band while allowing all other frequencies to pass.</p>

            <h3>How it works:</h3>
            <ol>
                <li><strong>Frequency Identification:</strong> Target frequencies (e.g. 50 Hz, 100 Hz,
                150 Hz) are specified</li>
                <li><strong>Filter Design:</strong> A narrow stop-band is created for each frequency</li>
                <li><strong>Application:</strong> The signal is passed through the filter,
                strongly attenuating the interference frequencies</li>
                <li><strong>Zero-Phase:</strong> Modern implementations use bidirectional
                filtering (forward-backward) to avoid phase shifts</li>
            </ol>

            <h3>Parameters:</h3>
            <ul>
                <li><strong>Center frequency (f₀):</strong> The frequency to suppress (e.g. 50 Hz)</li>
                <li><strong>Bandwidth (BW):</strong> Width of the stop-band around f₀</li>
                <li><strong>Quality Factor (Q):</strong> Q = f₀ / BW - higher values = narrower filters</li>
            </ul>

            <h3>Spectrum Fit Method:</h3>
            <p>This method uses a more sophisticated approach:</p>
            <ol>
                <li><strong>Segmentation:</strong> Signal is divided into overlapping windows</li>
                <li><strong>Spectral Analysis:</strong> FFT is applied to each window</li>
                <li><strong>Sinusoid Fitting:</strong> A sinusoidal curve is fitted to each
                interference frequency (amplitude, phase, frequency)</li>
                <li><strong>Subtraction:</strong> The estimated interference component is
                subtracted from the original signal</li>
                <li><strong>Smoothing:</strong> Transitions between windows are smoothed</li>
            </ol>

            <h3>CleanLine Method (MATLAB/EEGLAB):</h3>
            <p>CleanLine uses an advanced multi-taper approach:</p>
            <ol>
                <li><strong>Multi-Taper Spectral Estimation:</strong> Uses Slepian sequences (DPSS)
                for robust spectral estimation in each window</li>
                <li><strong>Statistical Testing:</strong> Thompson F-statistic tests whether
                line noise is significant at each frequency</li>
                <li><strong>Adaptive Fitting:</strong> For significant frequencies, fits sinusoids
                with time-varying amplitude and phase</li>
                <li><strong>Regression:</strong> Uses least-squares regression to estimate
                interference parameters in each window</li>
                <li><strong>Removal:</strong> Subtracts the estimated interference while
                preserving signal components</li>
            </ol>
            <p><em>Key parameters:</em> Window size (default 4s), window overlap (default 50%),
            significance level (p-value), frequency scan range.</p>

            <h2>Installation</h2>

            <h3>MNE-Python (already installed):</h3>
            <pre>pip install mne</pre>

            <h3>MATLAB CleanLine (optional):</h3>
            <ol>
                <li>Install MATLAB (license required)</li>
                <li>Install EEGLAB: <a href="https://sccn.ucsd.edu/eeglab/download.php">Download EEGLAB</a></li>
                <li>Install CleanLine plugin in EEGLAB:
                    <ul>
                        <li>In EEGLAB: File → Manage EEGLAB extensions → CleanLine</li>
                        <li>Or download from: <a href="https://github.com/sccn/cleanline">GitHub</a></li>
                    </ul>
                </li>
                <li>Install MATLAB Engine for Python:
                    <pre>cd "matlabroot\\extern\\engines\\python"
python setup.py install</pre>
                </li>
                <li>Add EEGLAB to MATLAB path (startup.m or manually)</li>
            </ol>

            <h3>MATLAB Engine only (optional):</h3>
            <ol>
                <li>Install MATLAB (license required)</li>
                <li>Install MATLAB Engine API:
                    <pre>cd "matlabroot\\extern\\engines\\python"
python setup.py install</pre>
                </li>
            </ol>

            <h3>Octave (optional, free):</h3>
            <ol>
                <li>Install Octave: <a href="https://octave.org/download">https://octave.org/download</a></li>
                <li>Install oct2py:
                    <pre>pip install oct2py</pre>
                </li>
            </ol>

            <h2>Sources and Further Information</h2>
            <ul>
                <li><a href="https://mne.tools/stable/generated/mne.filter.notch_filter.html">
                    MNE-Python Notch Filter Documentation</a></li>
                <li><a href="https://github.com/sccn/cleanline">CleanLine MATLAB Plugin (GitHub)</a></li>
                <li><a href="https://sccn.ucsd.edu/wiki/Cleanline">CleanLine EEGLAB Wiki</a></li>
                <li><a href="https://www.mathworks.com/help/signal/ref/iirnotch.html">
                    MATLAB iirnotch Documentation</a></li>
                <li><a href="https://octave.org/doc/interpreter/index.html">
                    GNU Octave Documentation</a></li>
                <li><a href="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6456018/">
                    Spectrum Interpolation Paper (Mewett et al., 2004)</a></li>
            </ul>
        </body>
        </html>
        """
