class NoteDetector:
    def __init__(self, notes_dict, tolerance=7):
        self.notes = notes_dict
        self.tolerance = tolerance

    def find_note(self, frequency):
        for note, freq in self.notes.items():
            if freq - self.tolerance <= frequency <= freq + self.tolerance:
                return note
        return None