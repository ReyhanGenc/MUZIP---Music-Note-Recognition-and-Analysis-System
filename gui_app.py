import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QTextEdit, QSplitter, QFrame, QMessageBox)
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

        self.lbl_image_display = QLabel("Henüz bir nota yüklenmedi.")
        self.lbl_image_display.setAlignment(Qt.AlignCenter)
        self.lbl_image_display.setStyleSheet("background-color: #111; border: 2px dashed #555;")
        left_layout.addWidget(self.lbl_image_display, stretch=1)

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

        self.btn_analyze_audio = QPushButton("Sesi Analiz Et")
        self.btn_analyze_audio.clicked.connect(self.start_audio_analysis)
        self.btn_analyze_audio.setEnabled(False)
        right_layout.addWidget(self.btn_analyze_audio)

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
        pixmap = QPixmap(path)
        scaled_pixmap = pixmap.scaled(self.lbl_image_display.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_image_display.setPixmap(scaled_pixmap)

    def start_image_analysis(self):
        self.btn_analyze_img.setEnabled(False)
        self.log(">> Görüntü analizi başlıyor...")
        
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
        if self.score_data and self.audio_data:
            self.btn_compare.setEnabled(True)
            self.log("💡 Muzip değerlendirme için hazır! Yeşil butona basın.")

    def run_comparison(self):
        self.log("\n================ SONUÇLAR ================")
        try:
            evaluator = PerformanceEvaluator()
            result = evaluator.compare(self.score_data, self.audio_data)

            accuracy = result.get('accuracy', 0)
            if 'pitch_accuracy' in result:
                accuracy = result['pitch_accuracy']
            
            self.log(f"BAŞARI ORANI: %{accuracy:.2f}")
            self.log(f"Toplam Nota: {result['total_notes']}")
            
            self.log("\n--- Detaylı Rapor ---")
            for item in result['feedback']:
                status = item['status']
                if status == "DOĞRU":
                    self.log(f"✅ {item.get('expected', item.get('expected_note'))}: Doğru çalındı.")
                elif status == "YANLIŞ":
                    self.log(f"❌ {item.get('expected', item.get('expected_note'))} yerine {item.get('played', item.get('played_note'))} çalındı.")
                elif status == "EKSİK":
                    self.log(f"⚠️ {item.get('expected', item.get('expected_note'))} notası atlandı.")
                elif status == "FAZLA":
                    self.log(f"⚠️ Fazladan {item.get('played', item.get('played_note'))} notası çalındı.")
            
            QMessageBox.information(self, "Analiz Bitti", f"Tebrikler! Başarı Oranı: %{accuracy:.2f}")

        except Exception as e:
            self.log(f"Karşılaştırma hatası: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MuzipApp()
    window.show()
    sys.exit(app.exec_())