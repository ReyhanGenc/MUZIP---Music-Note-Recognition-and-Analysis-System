import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QTextEdit, QSplitter, QFrame, QMessageBox, QScrollArea)
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal

try:
    from main import run_image_processing_module
    from audio_analysis.reader import AudioReader
    from audio_analysis.fft_processor import FFTProcessor
    from audio_analysis.note_detector import NoteDetector
    from audio_analysis.notes import NOTES
    from audio_analysis.analyzer import AudioAnalyzer
    from evaluator import PerformanceEvaluator
    import pyaudio
    import numpy as np
except ImportError as e:
    print(f"HATA: Modüller bulunamadı. Lütfen dosya yapısını kontrol edin.\nDetay: {e}")

class ImageWorker(QThread):
    finished = pyqtSignal(list, str)
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            score_data = run_image_processing_module(self.file_path)
            processed_img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                            'assets', 'output', 'detected_heads.png')
            
            if not os.path.exists(processed_img_path):
                processed_img_path = self.file_path
            
            self.finished.emit(score_data, processed_img_path)
        except Exception as e:
            self.error.emit(str(e))

class AudioWorker(QThread):
    finished = pyqtSignal(list)
    log = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            self.log.emit("Ses dosyası okunuyor...")
            reader = AudioReader(self.file_path)
            rate, data = reader.load()

            self.log.emit("Frekans analizi hazırlanıyor...")
            fft_proc = FFTProcessor(rate)
            detector = NoteDetector(NOTES)

            analyzer = AudioAnalyzer(data, rate, fft_proc, detector)
            
            self.log.emit("Analiz yapılıyor...")
            detected_notes = analyzer.analyze()
            
            self.finished.emit(detected_notes)
        except Exception as e:
            self.error.emit(str(e))

class LiveAudioWorker(QThread):
    note_detected = pyqtSignal(str, str, bool, int) # Beklenen, Duyulan, Doğru mu, Blok No
    status = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, score_data, bpm=120):
        super().__init__()
        self.score_data = score_data
        self.bpm = bpm
        self.is_running = True
        self.rate = 44100
        self.chunk_size = 2048

    def run(self):
        p = pyaudio.PyAudio()
        try:
            stream = p.open(format=pyaudio.paInt16, 
                            channels=1, 
                            rate=self.rate, 
                            input=True, 
                            output=True, # Hoparlör desteği
                            frames_per_buffer=self.chunk_size)
            
            # Click sesi üret (1000Hz sinüs)
            click_freq = 1000
            click_dur = 0.05
            t_click = np.linspace(0, click_dur, int(self.rate * click_dur), False)
            click_wave = (np.sin(2 * np.pi * click_freq * t_click) * 0.1) # Ses seviyesi %10
            # Fade out
            click_wave *= np.linspace(1, 0, len(click_wave))
            click_bytes = (click_wave * 32767).astype(np.int16).tobytes()

            from audio_analysis.fft_processor import FFTProcessor
            from audio_analysis.note_detector import NoteDetector
            from audio_analysis.notes import NOTES
            from audio_analysis.analyzer import AudioAnalyzer

            fft_proc = FFTProcessor(self.rate)
            detector = NoteDetector(NOTES)
            analyzer = AudioAnalyzer(rate=self.rate, fft_processor=fft_proc, note_detector=detector)
            
            duration_map = {"Onaltılık": 0.5, "Sekizlik": 1, "Dörtlük": 2, "İkilik": 4, "Birlik": 8}
            expected_timeline = []
            for snote in self.score_data:
                blocks = duration_map.get(snote['duration_type'], 2)
                for _ in range(blocks):
                    expected_timeline.append(snote['pitch'])
            
            block_dur = 60 / (self.bpm * 2) # 0.25sn
            beat_dur = 60 / self.bpm # 0.5sn
            
            self.status.emit("🎤 Mikrofon ve Metronom hazır. çalmaya başladığınızda analiz başlayacak...")
            
            started = False
            start_time = 0
            current_block = -1
            current_beat = -1

            while self.is_running:
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Sesi işle
                db_level = analyzer.get_db(analyzer.rms(audio_data))
                detected_pitch = analyzer.process_chunk(audio_data, 0, db_threshold=-40)
                
                if not started:
                    if db_level > -40: 
                        started = True
                        import time
                        start_time = time.time()
                        self.status.emit("🚀 Analiz başladı!")
                    else:
                        continue
                
                import time
                elapsed = time.time() - start_time
                
                # Metronom Sesi (Her Beat'te bir çal)
                beat_idx = int(elapsed / beat_dur)
                if beat_idx > current_beat:
                    current_beat = beat_idx
                    stream.write(click_bytes) # Metronom sesini çal
                
                # Hangi bloktayız?
                block_idx = int(elapsed / block_dur)
                
                if block_idx > current_block:
                    current_block = block_idx
                    if current_block < len(expected_timeline):
                        exp = expected_timeline[current_block]
                        played = detected_pitch if detected_pitch else "Sessizlik"
                        is_correct = (played == exp)
                        self.note_detected.emit(exp, played, is_correct, current_block + 1)
                    else:
                        self.status.emit("🏁 Score bitti.")
                        break
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            self.finished.emit([])

        except Exception as e:
            self.status.emit(f"Mikrofon/Metronom Hatası: {e}")
            p.terminate()

class MuzipApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Muzip 🎵")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; color: white; }
            QLabel { color: #e0e0e0; font-size: 14px; }
            QPushButton { 
                background-color: #6c3483; color: white; 
                border-radius: 5px; padding: 10px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #8e44ad; }
            QPushButton:disabled { background-color: #555; color: #888; }
            QTextEdit { background-color: #1e1e1e; color: #00ff00; font-family: Consolas; font-size: 13px; }
            QFrame { border: 1px solid #444; border-radius: 5px; }
        """)

        self.image_path = None
        self.audio_path = None
        self.score_data = []
        self.audio_data = []
        self.zoom_factor = 1.0
        self.original_pixmap = None

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        
        lbl_title_img = QLabel("🎼 Nota Kağıdı")
        lbl_title_img.setFont(QFont("Arial", 14, QFont.Bold))
        left_layout.addWidget(lbl_title_img)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: #111; border: 2px dashed #555;")
        
        self.lbl_image_display = QLabel("Henüz bir nota yüklenmedi.")
        self.lbl_image_display.setAlignment(Qt.AlignCenter)
        self.scroll_area.setWidget(self.lbl_image_display)
        left_layout.addWidget(self.scroll_area, stretch=1)
        
        # Zoom butonları
        zoom_layout = QHBoxLayout()
        btn_zoom_in = QPushButton("🔍+")
        btn_zoom_in.setFixedWidth(50)
        btn_zoom_in.clicked.connect(lambda: self.adjust_zoom(1.2))
        btn_zoom_out = QPushButton("🔍-")
        btn_zoom_out.setFixedWidth(50)
        btn_zoom_out.clicked.connect(lambda: self.adjust_zoom(0.8))
        btn_zoom_reset = QPushButton("Reset")
        btn_zoom_reset.setFixedWidth(80)
        btn_zoom_reset.clicked.connect(self.reset_zoom)
        
        zoom_layout.addWidget(btn_zoom_in)
        zoom_layout.addWidget(btn_zoom_out)
        zoom_layout.addWidget(btn_zoom_reset)
        zoom_layout.addStretch()
        left_layout.addLayout(zoom_layout)

        btn_load_img = QPushButton("Dosya Aç")
        btn_load_img.clicked.connect(self.load_image)
        left_layout.addWidget(btn_load_img)

        self.btn_analyze_img = QPushButton("Görüntüyü Analiz Et")
        self.btn_analyze_img.clicked.connect(self.start_image_analysis)
        self.btn_analyze_img.setEnabled(False)
        left_layout.addWidget(self.btn_analyze_img)

        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)

        lbl_title_audio = QLabel("🎤 Performans")
        lbl_title_audio.setFont(QFont("Arial", 14, QFont.Bold))
        right_layout.addWidget(lbl_title_audio)

        self.lbl_audio_status = QLabel("Ses dosyası bekleniyor...")
        right_layout.addWidget(self.lbl_audio_status)

        btn_load_audio = QPushButton("Ses Kaydı Yükle (.wav)")
        btn_load_audio.clicked.connect(self.load_audio)
        right_layout.addWidget(btn_load_audio)

        self.btn_analyze_audio = QPushButton("Sesi Analiz Et (Dosya)")
        self.btn_analyze_audio.clicked.connect(self.start_audio_analysis)
        self.btn_analyze_audio.setEnabled(False)
        right_layout.addWidget(self.btn_analyze_audio)

        self.btn_live_audio = QPushButton("🔴 CANLI PERFORMANS BAŞLAT")
        self.btn_live_audio.clicked.connect(self.start_live_analysis)
        self.btn_live_audio.setEnabled(False)
        self.btn_live_audio.setStyleSheet("background-color: #c0392b;")
        right_layout.addWidget(self.btn_live_audio)

        right_layout.addSpacing(20)
        lbl_title_result = QLabel("📊 Sonuç")
        lbl_title_result.setFont(QFont("Arial", 14, QFont.Bold))
        right_layout.addWidget(lbl_title_result)

        self.btn_compare = QPushButton("PUANLA VE DEĞERLENDİR")
        self.btn_compare.clicked.connect(self.run_comparison)
        self.btn_compare.setEnabled(False)
        self.btn_compare.setStyleSheet("background-color: #27ae60; font-size: 14px;")
        right_layout.addWidget(self.btn_compare)

        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setPlaceholderText("Muzip analiz için hazır...")
        right_layout.addWidget(self.txt_logs, stretch=1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([600, 400])

        main_layout.addWidget(splitter)

    # --- FONKSİYONLAR ---

    def log(self, message):
        self.txt_logs.append(f"{message}")
        self.txt_logs.verticalScrollBar().setValue(self.txt_logs.verticalScrollBar().maximum())

    def load_image(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Resim Seç', os.getenv('HOME'), "Image Files (*.png *.jpg *.bmp)")
        if fname:
            self.image_path = fname
            self.show_image(fname)
            self.btn_analyze_img.setEnabled(True)
            self.log(f"📄 Resim yüklendi: {os.path.basename(fname)}")

    def show_image(self, path):
        self.original_pixmap = QPixmap(path)
        self.zoom_factor = 1.0
        self.apply_zoom()

    def adjust_zoom(self, factor):
        self.zoom_factor *= factor
        if self.zoom_factor < 0.1: self.zoom_factor = 0.1
        if self.zoom_factor > 10.0: self.zoom_factor = 10.0
        self.apply_zoom()

    def reset_zoom(self):
        self.zoom_factor = 1.0
        self.apply_zoom()

    def apply_zoom(self):
        if self.original_pixmap:
            scaled_pixmap = self.original_pixmap.scaled(
                self.original_pixmap.size() * self.zoom_factor,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.lbl_image_display.setPixmap(scaled_pixmap)
            self.lbl_image_display.adjustSize()

    def start_image_analysis(self):
        self.btn_analyze_img.setEnabled(False)
        self.log(">> Görüntü analizi başlıyor (OpenCV + Gemini AI)...")
        self.log("   Not: Yapay zeka analizi birkaç saniye sürebilir.")
        
        self.img_worker = ImageWorker(self.image_path)
        self.img_worker.finished.connect(self.on_image_analysis_complete)
        self.img_worker.error.connect(lambda e: self.log(f"❌ Hata: {e}"))
        self.img_worker.start()

    def on_image_analysis_complete(self, data, processed_path):
        self.score_data = data
        self.show_image(processed_path)
        self.log(f"✅ Görüntü analizi bitti. {len(data)} nota bulundu.")
        
        self.log("\n----------------------------------")
        self.log("  TESPİT EDİLEN NOTALAR (REFERANS)")
        self.log("----------------------------------")
        
        for i, note in enumerate(data):
            nota_adi = note['pitch']
            sure = note['duration_type']
            self.log(f"#{i+1:<3} | {nota_adi:<5} | {sure}")
            
        self.log("----------------------------------\n")
        self.check_ready_to_compare()

    def start_live_analysis(self):
        if self.btn_live_audio.text() == "🔴 CANLI PERFORMANS BAŞLAT":
            self.btn_live_audio.setText("⏹ DURDUR")
            self.btn_live_audio.setStyleSheet("background-color: #7f8c8d;")
            self.log("\n>>> CANLI ANALİZ HAZIRLANIYOR...")
            
            self.live_worker = LiveAudioWorker(self.score_data)
            self.live_worker.status.connect(self.log)
            self.live_worker.note_detected.connect(self.on_live_note)
            self.live_worker.finished.connect(self.stop_live_analysis)
            self.live_worker.start()
        else:
            self.stop_live_analysis()

    def on_live_note(self, expected, played, is_correct, block_no):
        icon = "✅" if is_correct else "❌"
        msg = f"{block_no}. Blok | Beklenen: {expected:<5} | Duyulan: {played:<5} {icon}"
        self.log(msg)

    def stop_live_analysis(self):
        if hasattr(self, 'live_worker'):
            self.live_worker.is_running = False
        self.btn_live_audio.setText("🔴 CANLI PERFORMANS BAŞLAT")
        self.btn_live_audio.setStyleSheet("background-color: #c0392b;")
        self.log(">>> CANLI ANALİZ DURDURULDU.")

    def load_audio(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Ses Seç', os.getenv('HOME'), "Audio Files (*.wav)")
        if fname:
            self.audio_path = fname
            self.lbl_audio_status.setText(f"{os.path.basename(fname)}")
            self.lbl_audio_status.setStyleSheet("color: #85c1e9;")
            self.btn_analyze_audio.setEnabled(True)
            self.log(f"🎤 Ses dosyası seçildi: {os.path.basename(fname)}")

    def start_audio_analysis(self):
        self.btn_analyze_audio.setEnabled(False)
        self.log(">> Ses analizi başlıyor...")
        
        self.audio_worker = AudioWorker(self.audio_path)
        self.audio_worker.log.connect(self.log)
        self.audio_worker.finished.connect(self.on_audio_analysis_complete)
        self.audio_worker.error.connect(lambda e: self.log(f"❌ Hata: {e}"))
        self.audio_worker.start()

    def on_audio_analysis_complete(self, data):
        self.audio_data = data
        self.log(f"✅ Ses analizi bitti. {len(data)} nota algılandı.")
        
        self.log("\n----------------------------------")
        self.log("  DUYULAN NOTALAR (PERFORMANS)")
        self.log("----------------------------------")
        
        for i, note in enumerate(data):
            nota_adi = note['pitch']
            sure = f"{note['duration_seconds']:.2f} sn"
            
            self.log(f"#{i+1:<3} | {nota_adi:<5} | {sure}")
            
        self.log("----------------------------------\n")
        
        self.check_ready_to_compare()

    def check_ready_to_compare(self):
        if self.score_data:
            self.btn_live_audio.setEnabled(True)
        if self.score_data and self.audio_data:
            self.btn_compare.setEnabled(True)
            self.log("💡 Muzip değerlendirme için hazır! Yeşil butona basın.")

    def run_comparison(self):
        self.log("\n================ SONUÇLAR (120 BPM) ================")
        try:
            evaluator = PerformanceEvaluator()
            # 120 BPM ile zaman bloğu bazlı karşılaştırma
            result = evaluator.compare_with_bpm(self.score_data, self.audio_data, bpm=120)

            accuracy = result.get('accuracy', 0)
            self.log(f"METRONOM BAŞARI ORANI: %{accuracy:.2f}")
            self.log(f"Toplam Zaman Bloğu (0.25sn): {result['total_notes']}")
            
            self.log("\n--- Zaman Bazlı Detaylı Rapor ---")
            for item in result['feedback']:
                status = item['status']
                block_info = f"Blok {item['block']} ({item['time']:.2f}s)"
                
                if status == "DOĞRU":
                    self.log(f"✅ {block_info}: {item['expected_note']} - Doğru")
                else:
                    self.log(f"❌ {block_info}: Beklenen {item['expected_note']}, Duyulan {item['played_note']}")
            
            QMessageBox.information(self, "Analiz Bitti", f"Metronom Analizi Tamamlandı!\nBaşarı Oranı: %{accuracy:.2f}")

        except Exception as e:
            self.log(f"Karşılaştırma hatası: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MuzipApp()
    window.show()
    sys.exit(app.exec_())