import numpy as np

class FFTProcessor:
    def __init__(self, rate, chunk_size=2048):
        self.rate = rate
        self.chunk_size = chunk_size
        self.window = np.hanning(chunk_size)

    def get_dominant_frequency(self, chunk):
        if len(chunk) != self.chunk_size:
            chunk = np.pad(chunk, (0, self.chunk_size - len(chunk)))

        windowed = chunk * self.window
        fft_vals = np.fft.rfft(windowed, n=self.chunk_size * 2)
        mag = np.abs(fft_vals)
        freqs = np.fft.rfftfreq(self.chunk_size * 2, 1 / self.rate)

        hps = mag.copy()
        for h in range(2, 5):
            dec = mag[::h]
            hps[:len(dec)] *= dec

        idx = np.argmax(hps)
        peak = hps[idx]

        if peak < np.mean(hps) * 6:
            return 0

        freq = freqs[idx]

        while freq > 1000:
            freq /= 2
        while freq < 80:
            freq *= 2

        return freq
