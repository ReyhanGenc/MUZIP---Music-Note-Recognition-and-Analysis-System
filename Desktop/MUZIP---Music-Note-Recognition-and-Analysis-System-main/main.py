import os
import cv2
import json
import time

from image_processing import staff_detection 
from image_processing import symbol_analysis 

def map_duration_type(duration_key):
    duration_map = {
        "Half": "İkilik",
        "Quarter": "Dörtlük",
        "Eighth": "Sekizlik",
    }
    return duration_map.get(duration_key, "Bilinmeyen")


def run_image_processing_module(file_path):
    
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    print("------------------------")
    
    # 1. Ön İşleme
    try:
        original_img, processed_img = staff_detection.load_and_preprocess_image(file_path)
    except FileNotFoundError as e:
        print(f"Hata: {e}")
        return

    # 2. Dizek Tespiti ve Kaldırma
    staff_y_coords, marked_img, staff_removed_img = \
        staff_detection.detect_and_remove_staff_lines(processed_img.copy(), original_img.copy())
        
    print(f"\nTespit edilen dizek Y Koordinatları: {staff_y_coords}")
    
    # 3. Sembol Analizi ve Perde Tespiti
    detected_notes, total_blobs = symbol_analysis.detect_note_heads(staff_removed_img, staff_y_coords)
    
    final_notes = detected_notes 
    
    print(f"Nihai Algılanan Nota Sayısı: {len(final_notes)}")
    
    # 4. Sonuçları görsel olarak kaydetme
    temp_img = original_img.copy()
    
    # Notaları konuma göre sıralama
    final_notes = symbol_analysis.sort_notes_by_staff_rows(detected_notes, staff_y_coords)

    score_data_for_matching = []

    for i, note in enumerate(final_notes): 
        
        duration_tr = map_duration_type(note['duration_type'])

        # Nota başı etrafına kutu çizme
        cv2.rectangle(temp_img, (note['x'], note['y']), (note['x'] + note['w'], note['y'] + note['h']), (0, 255, 0), 2)
        
        # Perde bilgisini ve uzunluk bilgisini yazdırma
        info_text = f"{note['pitch_info']} | {duration_tr}"
        
        # Nota sırası yazdırma
        order_text = f"#{i+1}" 
        cv2.putText(temp_img, order_text, (note['x'], note['y'] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

        temp_img = symbol_analysis.put_text(temp_img, info_text, (note['x'], note['y'] + note['h'] + 15))

        # Veri yapısını oluşturma
        score_data_for_matching.append({
            "pitch": note['pitch_info'], 
            "duration_type": duration_tr,
            "order": i+1
        })


    # Dizek tespiti ve nota tespiti sonuçlarını kaydetme
    cv2.imwrite(os.path.join(output_dir, 'marked_staff_main.png'), marked_img)
    cv2.imwrite(os.path.join(output_dir, 'staff_removed_main.png'), staff_removed_img)
    cv2.imwrite(os.path.join(output_dir, 'detected_heads.png'), temp_img)
    
    print("------------------------")
    
    # Müzik terimlerini konsola yazdırma
    print("SIRA | UZUNLUK | PERDE")
    print("------------------------")
    for data in score_data_for_matching:
        print(f"#{data['order']:<3} | {data['duration_type']:<10} | {data['pitch']}")


    return score_data_for_matching
    
    
if __name__ == "__main__":
    # Test edilecek dosya yolu
    test_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'input', 'sample_score.png')
    
    run_image_processing_module(test_file_path)