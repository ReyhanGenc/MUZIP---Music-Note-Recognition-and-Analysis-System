from audio_analysis.reader import AudioReader
from audio_analysis.fft_processor import FFTProcessor
from audio_analysis.note_detector import NoteDetector
from audio_analysis.analyzer import AudioAnalyzer
from audio_analysis.notes import NOTES

filepath = "assets/input/sample_audio.wav"

reader = AudioReader(filepath)
rate, data = reader.load()

fft_proc = FFTProcessor(rate)
detector = NoteDetector(NOTES)

analyzer = AudioAnalyzer(data, rate, fft_proc, detector)
analyzer.analyze()
