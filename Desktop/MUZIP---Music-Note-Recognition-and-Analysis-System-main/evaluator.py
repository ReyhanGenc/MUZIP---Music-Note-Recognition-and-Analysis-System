import difflib

class PerformanceEvaluator:
    def __init__(self):
        pass

    def normalize_duration(self, audio_notes):
        if not audio_notes:
            return []
        
        durations = [n['duration_seconds'] for n in audio_notes]
        avg_dur = sum(durations) / len(durations)
        
        for note in audio_notes:
            ratio = note['duration_seconds'] / avg_dur
            if ratio < 0.7:
                note['duration_type'] = "Eighth"
            elif ratio > 1.5:
                note['duration_type'] = "Half"
            else:
                note['duration_type'] = "Quarter"
        return audio_notes

    def compare_with_bpm(self, score_notes, audio_notes, bpm=120):
        if not audio_notes or not score_notes:
            return {"accuracy": 0, "feedback": [{"status": "HATA", "msg": "Veri eksik."}]}

        # Zaman bloğu süresi (sn) 
        # 120 BPM -> 1 beat = 0.5 sn. Her beat 2 bloğa bölünürse -> 0.25 sn.
        block_dur = 60 / (bpm * 2)
        
        # 1. Beklenen (Score) notasını bloklara genişlet
        # Dörtlük (Quarter) = 2 blok, Sekizlik (Eighth) = 1 blok, İkilik (Half) = 4 blok
        duration_map = {"Sekizlik": 1, "Dörtlük": 2, "İkilik": 4}
        expected_timeline = []
        for snote in score_notes:
            blocks = duration_map.get(snote['duration_type'], 2) # Varsayılan dörtlük
            for _ in range(blocks):
                expected_timeline.append(snote['pitch'])
        
        # 2. Çalınan (Audio) notasını bloklara genişlet (İlk sesten itibaren başlar)
        t_start = audio_notes[0]['start_time']
        
        # Audio'nun toplam süresini bulalım (son nota sonuna kadar)
        last_note = audio_notes[-1]
        t_end = last_note['start_time'] + last_note['duration_seconds']
        total_audio_dur = t_end - t_start
        num_blocks = int(total_audio_dur / block_dur) + 1
        
        played_timeline = [None] * num_blocks
        
        for anote in audio_notes:
            rel_start = anote['start_time'] - t_start
            rel_end = rel_start + anote['duration_seconds']
            
            start_block = int(rel_start / block_dur)
            end_block = int(rel_end / block_dur)
            
            for b_idx in range(start_block, min(end_block + 1, num_blocks)):
                played_timeline[b_idx] = anote['pitch']

        # 3. İki timeline'ı karşılaştır
        correct_count = 0
        total_blocks = len(expected_timeline)
        feedback = []
        
        # Karşılaştırma döngüsü (Expected bazlı)
        for i in range(total_blocks):
            exp = expected_timeline[i]
            ply = played_timeline[i] if i < len(played_timeline) else "-"
            
            if exp == ply:
                correct_count += 1
                feedback.append({
                    "status": "DOĞRU",
                    "expected_note": exp,
                    "played_note": ply,
                    "block": i + 1,
                    "time": i * block_dur
                })
            else:
                feedback.append({
                    "status": "YANLIŞ",
                    "expected_note": exp,
                    "played_note": ply,
                    "block": i + 1,
                    "time": i * block_dur
                })

        accuracy = (correct_count / total_blocks) * 100 if total_blocks > 0 else 0
        
        return {
            "accuracy": accuracy,
            "feedback": feedback,
            "total_notes": total_blocks,
            "correct_notes": correct_count,
            "bpm_mode": True
        }