import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QTextEdit, QSplitter, QFrame, QMessageBox, QScrollArea,
                             QSpinBox)
from PyQt5.QtGui import QPixmap, QFont, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRect

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
            if score_data is None:
                score_data = []
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

import threading
import time

class MetronomeWorker(threading.Thread):
    def __init__(self, bpm, click_bytes, rate):
        super().__init__()
        self.bpm = bpm
        self.click_bytes = click_bytes
        self.rate = rate
        self.is_running = True
        self.daemon = True
        self.beat_interval = 60.0 / bpm

    def run(self):
        p_out = pyaudio.PyAudio()
        try:
            stream_out = p_out.open(format=pyaudio.paInt16, 
                                    channels=1, 
                                    rate=self.rate, 
                                    output=True)
            
            next_click_time = time.time()
            while self.is_running:
                current_time = time.time()
                if current_time >= next_click_time:
                    # Write metronome click asynchronously (blocks briefly for 50ms)
                    stream_out.write(self.click_bytes)
                    
                    # Compute next click target time using drift-free timing
                    next_click_time += self.beat_interval
                    
                    # Prevent falling behind if the system hangs temporarily
                    if time.time() > next_click_time + self.beat_interval:
                        next_click_time = time.time()
                
                # High-frequency sleep (1ms resolution) for perfect timing precision
                time.sleep(0.001)
                
            stream_out.stop_stream()
            stream_out.close()
        except Exception as e:
            print(f"Metronom Hatası: {e}")
        finally:
            p_out.terminate()

class LiveAudioWorker(QThread):
    note_detected = pyqtSignal(str, str, bool, int, int) # Beklenen, Duyulan, Doğru mu, Blok No, Nota İndeksi
    status = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, score_data, bpm=120):
        super().__init__()
        self.score_data = score_data
        self.bpm = bpm
        self.is_running = True
        self.rate = 44100
        self.chunk_size = 2048
        self.metronome = None

    def run(self):
        p = pyaudio.PyAudio()
        try:
            # Click sesi üret (1000Hz sinüs)
            click_freq = 1000
            click_dur = 0.05
            t_click = np.linspace(0, click_dur, int(self.rate * click_dur), False)
            click_wave = (np.sin(2 * np.pi * click_freq * t_click) * 0.1) # Ses seviyesi %10
            # Fade out
            click_wave *= np.linspace(1, 0, len(click_wave))
            click_bytes = (click_wave * 32767).astype(np.int16).tobytes()

            # --- GERİ SAYIM AŞAMASI (1 2 3 4 Son 2 3 4) ---
            countdown_labels = ["1", "2", "3", "4", "Son", "2", "3", "4"]
            p_out = pyaudio.PyAudio()
            stream_out = p_out.open(format=pyaudio.paInt16, 
                                    channels=1, 
                                    rate=self.rate, 
                                    output=True)
            
            beat_dur = 60.0 / self.bpm
            
            for label in countdown_labels:
                if not self.is_running:
                    break
                self.status.emit(f"⏱ GERİ SAYIM: [ {label} ]")
                stream_out.write(click_bytes)
                time.sleep(beat_dur)
                
            stream_out.stop_stream()
            stream_out.close()
            p_out.terminate()
            
            if not self.is_running:
                p.terminate()
                self.finished.emit([])
                return

            self.status.emit("🚀 BAŞLA!")

            # Microphone-only input stream (decoupled output path to prevent blocking)
            stream = p.open(format=pyaudio.paInt16, 
                            channels=1, 
                            rate=self.rate, 
                            input=True, 
                            frames_per_buffer=self.chunk_size)

            # Start decoupled metronome thread at the exact synchronized time
            self.metronome = MetronomeWorker(self.bpm, click_bytes, self.rate)
            self.metronome.start()

            from audio_analysis.fft_processor import FFTProcessor
            from audio_analysis.note_detector import NoteDetector
            from audio_analysis.notes import NOTES
            from audio_analysis.analyzer import AudioAnalyzer

            fft_proc = FFTProcessor(self.rate)
            detector = NoteDetector(NOTES)
            analyzer = AudioAnalyzer(rate=self.rate, fft_processor=fft_proc, note_detector=detector)
            
            duration_map = {"Onaltılık": 0.5, "Sekizlik": 1, "Dörtlük": 2, "İkilik": 4, "Birlik": 8}
            expected_timeline = []
            expected_timeline_note_indices = []
            for idx, snote in enumerate(self.score_data):
                blocks = duration_map.get(snote['duration_type'], 2)
                num_blocks = max(1, int(blocks))
                for _ in range(num_blocks):
                    expected_timeline.append(snote['pitch'])
                    expected_timeline_note_indices.append(idx)
            
            block_dur = 60 / (self.bpm * 2) # 0.25sn
            
            start_time = time.time()
            current_block = -1

            # Live performance notes collection
            live_played_notes = []
            current_live_note = None

            while self.is_running:
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Sesi işle
                db_level = analyzer.get_db(analyzer.rms(audio_data))
                detected_pitch = analyzer.process_chunk(audio_data, 0, db_threshold=-40)
                
                elapsed = time.time() - start_time
                
                # Real-time note tracking
                if db_level > -40 and detected_pitch: # If a note is heard above threshold
                    if current_live_note is None:
                        current_live_note = {
                            "pitch": detected_pitch,
                            "start_time": elapsed,
                            "last_seen_time": elapsed
                        }
                    elif current_live_note["pitch"] == detected_pitch:
                        current_live_note["last_seen_time"] = elapsed
                    else:
                        dur = current_live_note["last_seen_time"] - current_live_note["start_time"]
                        if dur >= 0.05:
                            live_played_notes.append({
                                "pitch": current_live_note["pitch"],
                                "start_time": current_live_note["start_time"],
                                "duration_seconds": max(0.1, dur)
                            })
                        current_live_note = {
                            "pitch": detected_pitch,
                            "start_time": elapsed,
                            "last_seen_time": elapsed
                        }
                else: # Silence
                    if current_live_note is not None:
                        dur = current_live_note["last_seen_time"] - current_live_note["start_time"]
                        if dur >= 0.05:
                            live_played_notes.append({
                                "pitch": current_live_note["pitch"],
                                "start_time": current_live_note["start_time"],
                                "duration_seconds": max(0.1, dur)
                            })
                        current_live_note = None

                # Hangi bloktayız?
                block_idx = int(elapsed / block_dur)
                
                if block_idx > current_block:
                    current_block = block_idx
                    if current_block < len(expected_timeline):
                        exp = expected_timeline[current_block]
                        note_idx = expected_timeline_note_indices[current_block]
                        played = detected_pitch if detected_pitch else "Sessizlik"
                        is_correct = (played == exp)
                        self.note_detected.emit(exp, played, is_correct, current_block + 1, note_idx)
                    else:
                        self.status.emit("🏁 Score bitti.")
                        break
            
            # Save any remaining note
            if current_live_note is not None:
                dur = elapsed - current_live_note["start_time"]
                live_played_notes.append({
                    "pitch": current_live_note["pitch"],
                    "start_time": current_live_note["start_time"],
                    "duration_seconds": max(0.1, dur)
                })

            if self.metronome:
                self.metronome.is_running = False
                
            stream.stop_stream()
            stream.close()
            p.terminate()
            self.finished.emit(live_played_notes)

        except Exception as e:
            self.status.emit(f"Mikrofon Hatası: {e}")
            if self.metronome:
                self.metronome.is_running = False
            p.terminate()

class MusicImageLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.current_note_rect = None # (x, y, w, h)
        self.zoom_factor = 1.0

    def set_current_note_rect(self, x, y, w, h, zoom_factor):
        if x is not None:
            self.current_note_rect = (x, y, w, h)
        else:
            self.current_note_rect = None
        self.zoom_factor = zoom_factor
        self.update()

    def clear_current_note(self):
        self.current_note_rect = None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.current_note_rect is not None and self.pixmap() is not None:
            painter = QPainter(self)
            
            # Sleek, vibrant modern blue color for cursor (neon/glow blue)
            pen = QPen(QColor(0, 150, 255, 230), 4)
            painter.setPen(pen)
            
            # Semi-transparent blue fill
            painter.setBrush(QColor(0, 150, 255, 50))
            
            x, y, w, h = self.current_note_rect
            
            scaled_x = int(x * self.zoom_factor)
            scaled_y = int(y * self.zoom_factor)
            scaled_w = int(w * self.zoom_factor)
            scaled_h = int(h * self.zoom_factor)
            
            # Center alignment offset
            pixmap_rect = self.pixmap().rect()
            label_rect = self.rect()
            
            offset_x = (label_rect.width() - pixmap_rect.width()) // 2
            offset_y = (label_rect.height() - pixmap_rect.height()) // 2
            
            offset_x = max(0, offset_x)
            offset_y = max(0, offset_y)
            
            scaled_x += offset_x
            scaled_y += offset_y
            
            # Draw beautiful rounded rectangle around the note
            painter.drawRoundedRect(QRect(scaled_x, scaled_y, scaled_w, scaled_h), 6, 6)
            painter.end()

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
        
        self.lbl_image_display = MusicImageLabel("Henüz bir nota yüklenmedi.")
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

        # Metronom Ayarı (BPM)
        bpm_layout = QHBoxLayout()
        lbl_bpm = QLabel("Metronom Tempo (BPM):")
        lbl_bpm.setStyleSheet("font-weight: bold; color: #fff;")
        
        self.spin_bpm = QSpinBox()
        self.spin_bpm.setRange(40, 240)
        self.spin_bpm.setValue(120)
        self.spin_bpm.setFixedWidth(80)
        self.spin_bpm.setStyleSheet("""
            QSpinBox {
                background-color: #1e1e1e;
                color: #00ff00;
                font-size: 14px;
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        bpm_layout.addWidget(lbl_bpm)
        bpm_layout.addWidget(self.spin_bpm)
        bpm_layout.addStretch()
        right_layout.addLayout(bpm_layout)

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
            
            # Güncel zoom oranını imlece de bildir
            if hasattr(self, 'lbl_image_display') and hasattr(self.lbl_image_display, 'zoom_factor'):
                self.lbl_image_display.zoom_factor = self.zoom_factor
                self.lbl_image_display.update()

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
            
            bpm_val = self.spin_bpm.value()
            self.live_worker = LiveAudioWorker(self.score_data, bpm=bpm_val)
            self.live_worker.status.connect(self.log)
            self.live_worker.note_detected.connect(self.on_live_note)
            self.live_worker.finished.connect(self.stop_live_analysis)
            self.live_worker.start()
        else:
            self.stop_live_analysis()

    def on_live_note(self, expected, played, is_correct, block_no, note_idx):
        icon = "✅" if is_correct else "❌"
        msg = f"{block_no}. Blok | Beklenen: {expected:<5} | Duyulan: {played:<5} {icon}"
        self.log(msg)

        # Gezinen imleci ve kaydırmayı güncelle
        if 0 <= note_idx < len(self.score_data):
            note = self.score_data[note_idx]
            x = note.get('x')
            y = note.get('y')
            w = note.get('w')
            h = note.get('h')
            if x is not None and y is not None:
                self.lbl_image_display.set_current_note_rect(x, y, w, h, self.zoom_factor)
                self.scroll_to_note(x, y, w, h)

    def scroll_to_note(self, x, y, w, h):
        if x is None or y is None:
            return
        scaled_x = int(x * self.zoom_factor)
        scaled_y = int(y * self.zoom_factor)
        scaled_w = int(w * self.zoom_factor)
        scaled_h = int(h * self.zoom_factor)
        
        viewport_width = self.scroll_area.viewport().width()
        viewport_height = self.scroll_area.viewport().height()
        
        target_h_scroll = scaled_x + (scaled_w // 2) - (viewport_width // 2)
        target_v_scroll = scaled_y + (scaled_h // 2) - (viewport_height // 2)
        
        self.scroll_area.horizontalScrollBar().setValue(target_h_scroll)
        self.scroll_area.verticalScrollBar().setValue(target_v_scroll)

    def stop_live_analysis(self, live_notes=None):
        if hasattr(self, 'live_worker'):
            self.live_worker.is_running = False
            if hasattr(self.live_worker, 'metronome') and self.live_worker.metronome:
                self.live_worker.metronome.is_running = False
        
        # Canlı çalınan notaları kaydet
        if isinstance(live_notes, list) and len(live_notes) > 0:
            self.audio_data = live_notes
            self.btn_compare.setEnabled(True)
            self.log(f"✅ Canlı performans kaydı tamamlandı. {len(live_notes)} nota algılandı.")
            self.log("💡 Muzip değerlendirme için hazır! Yeşil 'PUANLA VE DEĞERLENDİR' butonuna basın.")
        
        self.btn_live_audio.setText("🔴 CANLI PERFORMANS BAŞLAT")
        self.btn_live_audio.setStyleSheet("background-color: #c0392b;")
        if hasattr(self, 'lbl_image_display') and hasattr(self.lbl_image_display, 'clear_current_note'):
            self.lbl_image_display.clear_current_note()
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
        bpm_val = self.spin_bpm.value()
        self.log(f"\n================ SONUÇLAR ({bpm_val} BPM) ================")
        try:
            evaluator = PerformanceEvaluator()
            # Seçilen BPM ile zaman bloğu bazlı karşılaştırma
            result = evaluator.compare_with_bpm(self.score_data, self.audio_data, bpm=bpm_val)

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