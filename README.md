# MUZIP - Müzik Nota Tanıma ve Analiz Sistemi

Bu uygulama, nota kağıtlarını (image) analiz ederek dizekleri tespit eder, notaları perdelerine ve sürelerine göre ayırır ve kullanıcı arayüzü ile sonuçları görselleştirir.

## Özellikler

- **Dizek Tespiti:** Nota kağıdı üzerindeki dizek çizgilerini otomatik olarak bulur ve kaldırır.
- **Nota Analizi:** Nota başlarını tespit eder ve nota isimlerini (C, D, E...) belirler.
- **Görselleştirme:** Algılanan notaları orijinal resim üzerinde işaretler.
- **Kullanıcı Arayüzü:** Python tabanlı GUI ile kolay kullanım.

## Kurulum ve Çalıştırma

1. Gerekli kütüphaneleri yükleyin:
   ```bash
   pip install opencv-python numpy
   ```
2. Uygulamayı başlatın:
   ```bash
   python gui_app.py
   ```

## Proje Yapısı

- `main.py`: Ana işleme modülü.
- `gui_app.py`: Grafik kullanıcı arayüzü.
- `image_processing/`: Görüntü işleme ve nota analiz mantığı.
- `assets/`: Giriş ve çıkış örnekleri.

---
© 2026 - MUZIP Project
