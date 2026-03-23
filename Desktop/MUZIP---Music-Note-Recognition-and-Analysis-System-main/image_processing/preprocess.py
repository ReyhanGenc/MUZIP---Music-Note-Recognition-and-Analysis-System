import cv2
import numpy as np

def load_and_preprocess_image(file_path):
        
    # Dosya alma
    img = cv2.imread(file_path)
    if img is None:
        raise FileNotFoundError(f"Dosya bulunamadı veya açılamadı: {file_path}")

    # Gri tonlamaya dönüştürme
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # İkili görüntü (Binary) elde etmek için ters çevrilmiş eşikleme
    # Not: Müzik notaları siyah (0), arka plan beyaz (255)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    
    # Gürültü azaltma
    kernel = np.ones((2, 2), np.uint8)
    # Sembolleri kalınlaştırma
    processed_img = cv2.dilate(thresh, kernel, iterations=1)
    
    return img, processed_img