import cv2
import numpy as np
import os
from .preprocess import load_and_preprocess_image

def detect_and_remove_staff_lines(processed_img, original_img):
   
    # Hough Dönüşümü için geçici görüntüde yatay çizgileri vurgulama
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (processed_img.shape[1] // 2, 1))
    temp_img = cv2.erode(processed_img.copy(), horizontal_kernel, iterations=1) 
    temp_img = cv2.dilate(temp_img, horizontal_kernel, iterations=1)
    
    # HoughLinesP Uygulaması
    lines = cv2.HoughLinesP(temp_img, 
                            rho=1,           
                            theta=np.pi/180, 
                            threshold=150,   
                            minLineLength=processed_img.shape[1] // 3, 
                            maxLineGap=20)    

    staff_lines_y = []
    
    # Dizekleri kaldırma
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            
            if abs(y1 - y2) < 5: 
                staff_lines_y.append(y1)
                
                cv2.line(original_img, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.line(processed_img, (x1, y1), (x2, y2), (0), 1) 

    # Y koordinatlarını temizleme
    rounded_staff_lines_y = [int(y / 5) * 5 for y in staff_lines_y] 
    final_staff_coords = sorted(list(set(rounded_staff_lines_y)))
    
    # İkiye bölünen parçaları birleştirme
    closing_kernel = np.ones((5, 5), np.uint8)
    staff_removed_img_closed = cv2.morphologyEx(processed_img, cv2.MORPH_CLOSE, closing_kernel)
    
    return final_staff_coords, original_img, staff_removed_img_closed