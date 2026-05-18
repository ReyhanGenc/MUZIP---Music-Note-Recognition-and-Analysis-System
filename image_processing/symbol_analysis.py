import cv2
import numpy as np
from PIL import ImageFont, ImageDraw, Image

PITCH_NAMES = ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"] 

def put_text(img, text, position, font_path="arial.ttf", font_size=15, color=(0, 255, 0)):
    # OpenCV görüntüsünü (BGR) Pillow formatına (RGB) dönüştür
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    
    draw = ImageDraw.Draw(img_pil)
    
    # Fontu yükle (Windows için genellikle C:/Windows/Fonts/arial.ttf yolundadır)
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        # Font bulunamazsa varsayılan fontu kullan
        font = ImageFont.load_default()
    
    # Yazıyı yaz
    draw.text(position, text, font=font, fill=color)
    
    # Pillow görüntüsünü tekrar OpenCV formatına (BGR) dönüştür
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

# Notanın dikey konumunu, dizek grubunun alt ve üst sınırlarına göre orantısal olarak hesaplar.
def calculate_pitch_from_coords(center_y, staff_coords):

    if not staff_coords or len(staff_coords) < 5:
        return "Unknown"

    staff_group = sorted(staff_coords)
    bottom_line_y = staff_group[-1]
    total_staff_height = bottom_line_y - staff_group[0]

    # Dizekler arasının piksel değerinin yarısı hesaplandı
    half_space = total_staff_height / 8.0 

    # Alt çizgi (Mi4 çizgisi) referans alındı
    e4_ref_y = bottom_line_y

    start_pitch_index = 2
    start_octave = 4

    y_diff = e4_ref_y - center_y
    num_steps_float = y_diff / half_space
    num_steps = int(round(num_steps_float))

    final_index_raw = start_pitch_index + num_steps
    
    # Perde ve oktav ataması
    pitch_index = final_index_raw % 7
    if pitch_index < 0:
        pitch_index += 7
    
    octave_change = (final_index_raw - pitch_index) // 7
    final_octave = start_octave + octave_change
    
    final_pitch_name = PITCH_NAMES[pitch_index]

    return f"{final_pitch_name}{final_octave}"

# Nota başının doluluğunu kontrol eder.
def check_if_filled(img, x, y, w, h):

    if h < 4 or w < 4: return "Unknown"
    
    center_roi = img[y + h // 4 : y + 3 * h // 4, x + w // 4 : x + 3 * w // 4]
    
    if center_roi.size == 0: return "Unknown"
    
    white_pixels = cv2.countNonZero(center_roi)
    total_pixels = center_roi.size
    
    if (white_pixels / total_pixels) > 0.8:
        return "Half/Whole"
    else:
        return "Quarter/Shorter" 
def sort_notes_by_staff_rows(notes, staff_y_coords):
    if not notes or not staff_y_coords:
        return notes

    staff_y_coords = sorted(set(staff_y_coords))

    merged = [staff_y_coords[0]]
    for y in staff_y_coords[1:]:
        if y - merged[-1] > 5:
            merged.append(y)

    staff_rows = []
    for i in range(0, len(merged), 5):
        row = merged[i:i + 5]
        if len(row) == 5:
            staff_rows.append({
                "top": min(row),
                "bottom": max(row)
            })

    staff_rows.sort(key=lambda r: r["top"])

    rows_notes = {i: [] for i in range(len(staff_rows))}

    for note in notes:
        note_center_y = note["y"] + note["h"] / 2

        staff_index = min(
            range(len(staff_rows)),
            key=lambda i: abs(
                note_center_y - (staff_rows[i]["top"] + staff_rows[i]["bottom"]) / 2
            )
        )

        rows_notes[staff_index].append(note)

    sorted_notes = []
    for i in range(len(staff_rows)):
        row_notes = sorted(rows_notes[i], key=lambda n: n["x"])
        sorted_notes.extend(row_notes)

    return sorted_notes
def merge_note_heads_simple(heads, spacing):
    merged = []
    used = [False] * len(heads)

    for i in range(len(heads)):
        if used[i]:
            continue

        x, y, w, h = heads[i]
        cx = x + w / 2
        cy = y + h / 2

        min_x, min_y = x, y
        max_x, max_y = x + w, y + h

        used[i] = True

        for j in range(i + 1, len(heads)):
            if used[j]:
                continue

            x2, y2, w2, h2 = heads[j]
            cx2 = x2 + w2 / 2
            cy2 = y2 + h2 / 2

            # Kuyruklar genellikle nota başının altında veya üstünde olduğu için dikey (Y) toleransı artırıldı
            # Yatay (X) toleransı ise aynı hizada olduklarını doğrulamak için daha sıkı hale getirildi
            vertical_near = abs(cy - cy2) < spacing * 1.2
            horizontal_near = abs(cx - cx2) < spacing * 0.6

            if horizontal_near and vertical_near:
                min_x = min(min_x, x2)
                min_y = min(min_y, y2)
                max_x = max(max_x, x2 + w2)
                max_y = max(max_y, y2 + h2)
                used[j] = True

        merged.append((min_x, min_y, max_x - min_x, max_y - min_y))

    return merged
def is_valid_note_head(bbox, spacing):
    x, y, w, h = bbox

    # Nota başından küçük kutuları elemeyi garanti altına almak için alt sınır sıkılaştırıldı
    if not (0.85 * spacing < w < 2.0 * spacing):
        return False
    if not (0.82 * spacing < h < 1.6 * spacing):
        return False

    aspect_ratio = w / h
    # Nota başı yatay elipstir, aspect ratio kontrolü
    if not (0.90 < aspect_ratio < 1.9): 
        return False

    return True
def detect_stem_direction(img, bbox, spacing):
    x, y, w, h = bbox

    # Saplar yukarı gidiyorsa nota başının sağındadır (x + w - 2)
    # Saplar aşağı gidiyorsa nota başının solundadır (x + 2)
    up_strip = img[max(0, y - int(3.5 * spacing)):y, max(0, x + w - 3):min(img.shape[1], x + w)]
    down_strip = img[y+h:min(img.shape[0], y+h + int(3.5 * spacing)), max(0, x):min(img.shape[1], x + 3)]

    up_pixels = cv2.countNonZero(up_strip) if up_strip.size > 0 else 0
    down_pixels = cv2.countNonZero(down_strip) if down_strip.size > 0 else 0

    if up_pixels > down_pixels and up_pixels > 5:
        return "up"
    elif down_pixels > up_pixels and down_pixels > 5:
        return "down"
    
    return None

def find_stem_end(img, start_x, start_y, direction, max_len):
    h, w = img.shape[:2]

    step = -1 if direction == "up" else 1
    y = start_y

    for _ in range(max_len):
        y += step
        if y < 0 or y >= h:
            break

        pixel = img[y, start_x]
        # Sap çizgisi beyazdır, siyah arka plana (0) ulaştığımızda sapın sonuna gelmişizdir.
        if pixel < 50:
            return y - step

    return y

def has_flag_from_stem(img, bbox, spacing):
    x, y, w, h = bbox

    # Bu nota kağıdında her nota bayrağı/kuyruğu alt kısımda (nota başının altında) yer alır.
    # Nota başının dikey olarak altından 1.0 * spacing ile 3.5 * spacing arası bayrak bölgesidir.
    y_start = y + h + int(1.0 * spacing)
    y_end = y + h + int(3.5 * spacing)
    
    if y_start >= img.shape[0]:
        return False
    y_end = min(img.shape[0], y_end)

    # Sapın sol tarafında (sol sapın sağ kısmı) veya sağ tarafında (sağ sapın sağ kısmı) bayrak yoğunluğunu tara
    sol_stem_x = x + 2
    sol_roi = img[y_start:y_end, max(0, sol_stem_x + 2):min(img.shape[1], sol_stem_x + int(1.8 * spacing))]

    sag_stem_x = x + w - 2
    sag_roi = img[y_start:y_end, max(0, sag_stem_x + 2):min(img.shape[1], sag_stem_x + int(1.8 * spacing))]

    sol_pixels = cv2.countNonZero(sol_roi) if sol_roi.size > 0 else 0
    sag_pixels = cv2.countNonZero(sag_roi) if sag_roi.size > 0 else 0

    # Alt kısımda sapın yanında belirgin bir piksel yoğunluğu (kuyruk) varsa sekizliktir
    if sol_pixels > 4 or sag_pixels > 4:
        return True

    return False

def is_note_head_filled(img, bbox):
    x, y, w, h = bbox

    roi = img[y:y+h, x:x+w]
    if roi.size == 0:
        return False

    gray = roi
    if len(roi.shape) == 3:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    cx, cy = w // 2, h // 2
    r = int(min(w, h) * 0.25)

    mask = np.zeros(binary.shape, dtype=np.uint8)
    cv2.circle(mask, (cx, cy), r, 255, -1)

    filled_pixels = cv2.countNonZero(
        cv2.bitwise_and(binary, mask)
    )
    total_pixels = cv2.countNonZero(mask)

    fill_ratio = filled_pixels / total_pixels

    return fill_ratio > 0.55

def determine_duration(img, bbox, spacing):
    # Bu fonksiyon içi mantıkta is_note_head_filled içi boş (half note) olduğunda True döner
    is_empty_head = is_note_head_filled(img, bbox)

    if is_empty_head:
        return "Half"      

    if has_flag_from_stem(img, bbox, spacing):
        return "Eighth"

    return "Quarter"       


def detect_note_heads(staff_removed_img, staff_coords):
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        staff_removed_img, connectivity=8, ltype=cv2.CV_32S
    )

    detected_notes = []
    if not staff_coords:
        return [], 0

    sorted_coords = sorted(list(set(staff_coords)))
    unique_coords = []
    if sorted_coords:
        unique_coords.append(sorted_coords[0])
        for i in range(1, len(sorted_coords)):
            if sorted_coords[i] - sorted_coords[i-1] > 5:
                unique_coords.append(sorted_coords[i])

    staff_rows = []
    for i in range(0, len(unique_coords), 5):
        row = unique_coords[i:i+5]
        if len(row) == 5:
            staff_rows.append({'top': min(row), 'bottom': max(row), 'coords': row})

    for i in range(1, num_labels):
        x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        
        center_y = y + h / 2
        current_staff = min(staff_rows, key=lambda r: abs(center_y - (r['top'] + r['bottom']) / 2))
        spacing = (current_staff['bottom'] - current_staff['top']) / 4

        # Sol anahtarını ve donanımı elemek için dinamik ofset
        staff_index = next((idx for idx, r in enumerate(staff_rows) if r == current_staff), 0)
        
        if staff_index == 0:
            left_margin = 6.0 * spacing 
        else:
            left_margin = 3.5 * spacing 
        
        if x < left_margin:
            continue

        # Bileşen doluluk (Solidity) kontrolü: Alan / Bbox Alanı
        area = stats[i, cv2.CC_STAT_AREA]
        solidity = area / (w * h)
        
        if solidity < 0.22: 
            continue
            
        # Nota başları alanı dizek aralığı karesine göre (0.52 - 3.5 katı)
        # Min alan 0.52'ye çekilerek bayrak/kuyruk parçalarının bağımsız nota olarak algılanması tamamen önlendi.
        if not (0.52 * (spacing**2) < area < 3.5 * (spacing**2)):
            continue

        mask = np.zeros(staff_removed_img.shape, dtype=np.uint8)
        mask[labels == i] = 255
        
        # Kernel boyutunu dizek aralığına göre ayarla (0.35 katı - biraz küçültüldü)
        k_size = max(3, int(spacing * 0.35))
        if k_size % 2 == 0: k_size += 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        
        heads_only = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        note_head_contours, _ = cv2.findContours(
            heads_only, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        raw_heads = [cv2.boundingRect(cnt) for cnt in note_head_contours]

        merged_heads = merge_note_heads_simple(raw_heads, spacing)

        for (ox, oy, ow, oh) in merged_heads:
            if not is_valid_note_head((ox, oy, ow, oh), spacing):
                continue

            head_center_y = int(oy + oh / 2)

            pitch_info = calculate_pitch_from_coords(
                head_center_y,
                current_staff['coords']
            )
            duration_type = determine_duration(
                staff_removed_img,
                (ox, oy, ow, oh),
                spacing
            )

            detected_notes.append({
                "x": ox,
                "y": oy,
                "w": ow,
                "h": oh,
                "center_y": head_center_y,
                "pitch_info": pitch_info,
                "duration_type": duration_type
            })

    return detected_notes, len(detected_notes)

