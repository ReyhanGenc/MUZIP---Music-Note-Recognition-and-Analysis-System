import numpy as np
from collections import deque, Counter

class AudioAnalyzer:
    def __init__(self, data, rate, fft_processor, note_detector,
                 chunk_size=2048, threshold=0.01):

        self.data = data
        self.rate = rate
        self.fft = fft_processor
        self.detector = note_detector
        self.chunk_size = chunk_size
        self.threshold = threshold

        self.current_note = None
        self.note_start_idx = None

        self.note_buffer = deque(maxlen=4)

        self.silence_start_idx = None
        self.min_silence = int(0.05 * self.rate)
        
        self.detected_notes_list = []

    def rms(self, x):
        return np.sqrt(np.mean(x**2))

    def analyze(self):
        self.detected_notes_list = []
        
        idx = 0
        total = len(self.data)

        print(f"Analiz başlıyor... ({total/self.rate:.2f} sn)")

        while idx < total:
            chunk = self.data[idx:idx+self.chunk_size]
            if len(chunk) < self.chunk_size:
                break

            e = self.rms(chunk)

            if e > self.threshold:
                freq = self.fft.get_dominant_frequency(chunk)
                note = self.detector.find_note(freq)
                self.note_buffer.append(note)
            else:
                self.note_buffer.append(None)

            stabilized_note = None
            if len(self.note_buffer) == self.note_buffer.maxlen:
                n, c = Counter(self.note_buffer).most_common(1)[0]
                if c >= 3:
                    stabilized_note = n

            if stabilized_note is None:
                if self.current_note is not None:
                    if self.silence_start_idx is None:
                        self.silence_start_idx = idx
                    elif idx - self.silence_start_idx >= self.min_silence:
                        self._save(idx)
                        self.current_note = None
                        self.note_start_idx = None
                        self.silence_start_idx = None
                idx += self.chunk_size
                continue
            else:
                self.silence_start_idx = None

            if self.current_note is None:
                self.current_note = stabilized_note
                self.note_start_idx = idx

            elif stabilized_note != self.current_note:
                self._save(idx)
                self.current_note = stabilized_note
                self.note_start_idx = idx

            idx += self.chunk_size

        if self.current_note:
            self._save(total)
            
        return self.detected_notes_list

    def _save(self, idx):
        if self.note_start_idx is None:
            return

        dur = (idx - self.note_start_idx) / self.rate
        
        if dur >= 0.10: 
            print(f"Nota: {self.current_note}, Süre: {dur:.2f} sn")
            
            self.detected_notes_list.append({
                "pitch": self.current_note,
                "duration_seconds": dur,
                "start_time": self.note_start_idx / self.rate
            })