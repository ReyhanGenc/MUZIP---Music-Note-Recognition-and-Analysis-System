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

    def compare(self, score_notes, audio_notes):
        ref_pitches = [n['pitch'] for n in score_notes]
        played_pitches = [n['pitch'] for n in audio_notes]

        matcher = difflib.SequenceMatcher(None, ref_pitches, played_pitches)
        
        correct_count = 0
        feedback = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            
            if tag == 'equal':
                for k in range(j2 - j1):
                    original = score_notes[i1 + k]
                    played = audio_notes[j1 + k]
                    correct_count += 1
                    feedback.append({
                        "status": "DOĞRU",
                        "expected": original['pitch'],
                        "played": played['pitch'],
                        "msg": "Mükemmel!"
                    })
            
            elif tag == 'replace':
                for k in range(max(i2 - i1, j2 - j1)):
                    exp = score_notes[i1 + k]['pitch'] if i1 + k < i2 else "-"
                    ply = audio_notes[j1 + k]['pitch'] if j1 + k < j2 else "-"
                    feedback.append({
                        "status": "YANLIŞ",
                        "expected": exp,
                        "played": ply,
                        "msg": f"{exp} yerine {ply} çaldınız."
                    })
            
            elif tag == 'delete':
                for k in range(i1, i2):
                    feedback.append({
                        "status": "EKSİK",
                        "expected": score_notes[k]['pitch'],
                        "played": "-",
                        "msg": "Notayı atladınız."
                    })
            
            elif tag == 'insert':
                for k in range(j1, j2):
                    feedback.append({
                        "status": "FAZLA",
                        "expected": "-",
                        "played": audio_notes[k]['pitch'],
                        "msg": "Gereksiz nota çaldınız."
                    })

        total_notes = len(score_notes)
        accuracy = (correct_count / total_notes) * 100 if total_notes > 0 else 0
        
        return {
            "accuracy": accuracy,
            "feedback": feedback,
            "total_notes": total_notes,
            "correct_notes": correct_count
        }