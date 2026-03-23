import numpy as np
from scipy.io import wavfile

class AudioReader:
    def __init__(self, filepath):
        self.filepath = filepath
        self.rate = None
        self.data = None

    def load(self):
        self.rate, data = wavfile.read(self.filepath)

        if len(data.shape) > 1:
            data = data.mean(axis=1)

        self.data = data.astype(np.float32)
        return self.rate, self.data