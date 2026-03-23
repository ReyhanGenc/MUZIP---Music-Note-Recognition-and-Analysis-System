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

            same_row = abs(cy - cy2) < spacing * 0.4
            close_x = abs(cx - cx2) < spacing * 0.9

            if same_row and close_x:
                min_x = min(min_x, x2)
                min_y = min(min_y, y2)
                max_x = max(max_x, x2 + w2)
                max_y = max(max_y, y2 + h2)
                used[j] = True

        merged.append((min_x, min_y, max_x - min_x, max_y - min_y))

    return merged
def is_valid_note_head(bbox, spacing):
    _, _, w, h = bbox

    if not (0.6 * spacing < w < 1.8 * spacing):
        return False
    if not (0.6 * spacing < h < 1.8 * spacing):
        return False

    aspect_ratio = w / h
    if not (0.6 < aspect_ratio < 1.6):
        return False

    area = w * h
    if not (0.3 * spacing * spacing < area < 4.0 * spacing * spacing):
        return False

    return True
def detect_stem_direction(img, bbox, spacing):
    x, y, w, h = bbox

    stem_x = x + w // 2

    upper_roi = img[max(0, y - int(3 * spacing)):y, stem_x-1:stem_x+1]
    lower_roi = img[y+h:y+h + int(3 * spacing), stem_x-1:stem_x+1]

    upper_black = cv2.countNonZero(255 - upper_roi)
    lower_black = cv2.countNonZero(255 - lower_roi)

    if upper_black > lower_black:
        return "up"
    elif lower_black > upper_black:
        return "down"
    else:
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
        if pixel > 200:
            return y

    return y

def has_flag_from_stem(img, bbox, spacing):
    x, y, w, h = bbox

    direction = detect_stem_direction(img, bbox, spacing)
    if direction is None:
        return False

    stem_x = x + w // 2
    stem_start_y = y if direction == "up" else y + h

    stem_end_y = find_stem_end(
        img,
        stem_x,
        stem_start_y,
        direction,
        max_len=int(4 * spacing)
    )

    check_y = stem_end_y + (-2 if direction == "up" else 2)

    side_rois = [
        (stem_x + 1, stem_x + int(1.5 * spacing)),   
        (stem_x - int(1.5 * spacing), stem_x - 1)    
    ]

    for x1, x2 in side_rois:
        roi = img[
            max(0, check_y - 2): check_y + 2,
            max(0, x1): max(0, x2)
        ]

        if roi.size == 0:
            continue

        black_ratio = cv2.countNonZero(255 - roi) / roi.size

        if black_ratio > 0.15:
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
    not_filled = is_note_head_filled(img, bbox)

    if not_filled:
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

        if y < (current_staff['top'] - spacing * 5) or y > (current_staff['bottom'] + spacing * 5):
            continue
        if x < 80: 
            continue

        mask = np.zeros(staff_removed_img.shape, dtype=np.uint8)
        mask[labels == i] = 255
        
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
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

