import os
import cv2
import json
import time

from image_processing import staff_detection 
from image_processing import symbol_analysis 
from image_processing.gemini_analyzer import GeminiMusicAnalyzer

def map_duration_type(duration_key):
    duration_map = {
        "Whole": "Birlik",
        "Half": "İkilik",
        "Quarter": "Dörtlük",
        "Eighth": "Sekizlik",
        "Sixteenth": "Onaltılık"
    }
    return duration_map.get(duration_key, "Bilinmeyen")

def map_accidental_type(accidental_key):
    accidental_map = {
        "Sharp": "#",
        "Flat": "b",
        "Natural": "n",
        "None": ""
    }
    return accidental_map.get(accidental_key, "")


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
        cv2.putText(temp_img, order_text, (note['x'], note['y'] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

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
    
    labeled_image_path = os.path.join(output_dir, 'detected_heads.png')
    cv2.imwrite(labeled_image_path, temp_img)
    
    # --- GEMINI ANALİZ ADIMI (AKILLI KIRPMA İLE) ---
    print("\n[AI] Gemini Flash ile nota süreleri ve arızalar analiz ediliyor (Kırpılmış Görsel)...")
    
    # 1. Aktif alanı belirle (Dizekler ve notaların olduğu bölge)
    h_orig, w_orig = temp_img.shape[:2]
    
    all_y = list(staff_y_coords) + [n['y'] for n in final_notes] + [n['y'] + n['h'] for n in final_notes]
    all_x = [n['x'] for n in final_notes] + [n['x'] + n['w'] for n in final_notes]
    
    if not all_y or not all_x:
        # Eğer nota veya dizek bulunamadıysa tüm resmi kullan (fallback)
        crop_box = (0, 0, w_orig, h_orig)
    else:
        margin = 50
        ymin_crop = max(0, min(all_y) - margin)
        ymax_crop = min(h_orig, max(all_y) + margin)
        xmin_crop = max(0, min(all_x) - margin)
        xmax_crop = min(w_orig, max(all_x) + margin)
        crop_box = (int(xmin_crop), int(ymin_crop), int(xmax_crop), int(ymax_crop))

    # 2. Resmi kırp ve kaydet
    crop_img = temp_img[crop_box[1]:crop_box[3], crop_box[0]:crop_box[2]]
    crop_path = os.path.join(output_dir, 'gemini_crop.png')
    cv2.imwrite(crop_path, crop_img)
    
    # 3. Gemini analizini çağır (Orijinal boyut ve crop bilgisini gönder)
    gemini = GeminiMusicAnalyzer()
    gemini_results = gemini.analyze_notes(crop_path, original_size=(w_orig, h_orig), crop_box=crop_box)
    
    # Gemini'den gelen verileri mevcut notalarla eşleştirme
    gemini_map = {item['order']: item for item in gemini_results if 'order' in item}
    
    print("\n------------------------")
    # Müzik terimlerini konsola yazdırma
    print("SIRA | UZUNLUK | PERDE | ARIZA")
    print("------------------------")
    
    final_score_data = []

    for i, note in enumerate(score_data_for_matching):
        order = note['order']
        
        # Eğer Gemini sonucu varsa, OpenCV'den geleni ez
        if order in gemini_map:
            gemini_duration = gemini_map[order].get('duration', 'Quarter')
            gemini_accidental = gemini_map[order].get('accidental', 'None')
            
            note['duration_type'] = map_duration_type(gemini_duration)
            note['accidental'] = map_accidental_type(gemini_accidental)
            
            # Mavi Kutu Çizme (Eğer koordinat verisi varsa)
            accidental_box = gemini_map[order].get('accidental_box_2d')
            if accidental_box and len(accidental_box) == 4:
                h_img, w_img = temp_img.shape[:2]
                ymin, xmin, ymax, xmax = accidental_box
                
                # Normalize koordinatları (0-1000) piksele çevir
                # Normalize koordinatları (0-1000) piksele çevir
                # Ölçeklendirme ve belirginleştirme: Biraz padding ekle
                padding = 3
                px_ymin = max(0, int(ymin * h_img / 1000) - padding)
                px_xmin = max(0, int(xmin * w_img / 1000) - padding)
                px_ymax = min(h_img, int(ymax * h_img / 1000) + padding)
                px_xmax = min(w_img, int(xmax * w_img / 1000) + padding)
                
                # Mavi kutu çiz (# arızasının üzerine) - Kalınlığı artırıldı (3)
                cv2.rectangle(temp_img, (px_xmin, px_ymin), (px_xmax, px_ymax), (255, 0, 0), 3)
        else:
            note['accidental'] = "" # Varsayılan boş

        # Final pitch (perde ismi + arıza)
        final_pitch = f"{note['pitch']}{note['accidental']}"
        
        print(f"#{note['order']:<3} | {note['duration_type']:<10} | {note['pitch']:<5} | {note['accidental']:<5}")
        
        final_score_data.append({
            "pitch": final_pitch,
            "duration_type": note['duration_type'], # 'Dörtlük' vb.
            "order": order
        })

    # Gemini sonuçlarıyla (mavi kutularla) güncellenmiş resmi tekrar kaydet
    cv2.imwrite(labeled_image_path, temp_img)

    return final_score_data
    
    
if __name__ == "__main__":
    # Test edilecek dosya yolu
    test_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'input', 'sample_score.png')
    
    run_image_processing_module(test_file_path)