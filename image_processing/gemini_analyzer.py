import os
from google import genai
import json
import re
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# API Key'i yapılandır
API_KEY = os.getenv("GEMINI_API_KEY")
# Yeni SDK'da client üzerinden işlem yapılır

class GeminiMusicAnalyzer:
    def __init__(self):
        self.client = genai.Client(api_key=API_KEY)
        self.model_id = None
        self.find_best_model()

    def find_best_model(self):
        """Kullanıcının API anahtarı ile erişebileceği en iyi modeli bulur."""
        print("\n[Sistem] Erişilebilir modeller kontrol ediliyor...")
        try:
            available_models = [m.name for m in self.client.models.list() if m.supported_actions and 'generateContent' in m.supported_actions]
            print(f"[Sistem] API Anahtarınızın erişebildiği modeller: {available_models}")
            
            # Tercih sirasina gore modeller
            preferences = [
                'gemini-2.5-flash',
                'gemini-2.5-pro',
                'gemini-2.0-flash',
                'gemini-2.0-flash-exp',
                'gemini-1.5-flash-latest',
                'gemini-1.5-flash',
                'gemini-1.5-pro',
                'gemini-pro'
            ]
            
            selected_model = None
            for pref in preferences:
                # Flexible matching for models/ prefix
                pref_full = f"models/{pref}" if not pref.startswith("models/") else pref
                pref_short = pref.replace("models/", "")
                
                if pref_full in available_models:
                    selected_model = pref_full
                    break
                elif pref_short in available_models:
                    selected_model = pref_short
                    break
            
            if not selected_model and available_models:
                selected_model = available_models[0]
            
            if selected_model:
                print(f"[AI] Seçilen Model: {selected_model}")
                self.model_id = selected_model
            else:
                print("[HATA] Hiçbir üretken model bulunamadı. Lütfen API anahtarınızı kontrol edin.")
        except Exception as e:
            print(f"[HATA] Model listeleme başarısız: {e}")
            # Manuel fallback
            self.model_id = 'gemini-1.5-flash'

    def analyze_notes(self, image_path, original_size=None, crop_box=None):
        if not self.model_id:
            print("[HATA] Model yüklenemediği için analiz yapılamıyor.")
            return []

        try:
            img = Image.open(image_path)
            
            prompt = """
            Müzik notası uzmanı ve görsel analiz yeteneği yüksek bir AI olarak bu görseli analiz et. 
            Görselde her bir nota üzerinde kırmızı renkli numaralar (#1, #2, #3...) bulunmaktadır.
            
            Öncelikle nota kağıdının Donanımını (Key Signature) belirle.
            
            Her bir numaralı nota için şu bilgileri içeren bir JSON listesi döndür:
            - "order": Notanın üzerindeki numara (1, 2, 3 vb.)
            - "duration": Notanın süresi (Whole, Half, Quarter, Eighth, Sixteenth)
            - "accidental": Notanın hemen SOLUNDA (bitişiğinde) bir işaret olup olmadığını ÇOK DİKKATLİ kontrol et. 
               - Seçenekler: "Sharp" (#), "Flat" (b), "Natural" (naturel işareti), "None".
               - ÖNEMLİ: Bazı diyez/bemol işaretleri silik veya küçük olabilir. Eğer notanın solunda herhangi bir ek sembol varsa, bu mutlaka bir arıza işaretidir.
            - "accidental_box_2d": Eğer "accidental" "None" DEĞİLSE, bu işaretin tam koordinatlarını [ymin, xmin, ymax, xmax] (0-1000 arası) olarak döndür. 
               - Kutu sadece arıza işaretini (diyez/bemol/naturel) kapsamalıdır.
            
            Sadece JSON listesi döndür. Cevapta başka hiçbir metin olmasın.
            Örnek format: [{"order": 1, "duration": "Quarter", "accidental": "Sharp", "accidental_box_2d": [100, 200, 150, 250]}]
            """

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[prompt, img]
            )
            
            # Windows terminalleri için güvenli yazdırma (Türkçe karakterlerde çökmesini önler)
            try:
                print(f"\n--- [Gemini Analiz Çıktısı] ---\n{response.text}\n")
            except Exception:
                print("\n--- [Gemini Analiz Çıktısı] --- (Metin alındı ancak terminale yazdırılamadı)")
            
            json_str = response.text
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            
            try:
                results = json.loads(json_str.strip())
            except json.JSONDecodeError as je:
                print(f"[HATA] JSON ayristirma hatasi: {je}")
                print(f"[HATA] Ham metin: {json_str[:200]}...")
                return []

            # Koordinatları orijinal resme göre yeniden hesapla (eğer crop varsa)
            if crop_box and original_size:
                crop_xmin, crop_ymin, crop_xmax, crop_ymax = crop_box
                crop_w = crop_xmax - crop_xmin
                crop_h = crop_ymax - crop_ymin
                orig_w, orig_h = original_size

                for item in results:
                    box = item.get('accidental_box_2d')
                    if box and len(box) == 4:
                        ymin, xmin, ymax, xmax = box
                        # Kırpılmış resimdeki 0-1000 koordinatlarını piksele çevir, sonra orijinal resme ekle
                        abs_ymin = crop_ymin + (ymin * crop_h / 1000)
                        abs_xmin = crop_xmin + (xmin * crop_w / 1000)
                        abs_ymax = crop_ymin + (ymax * crop_h / 1000)
                        abs_xmax = crop_xmin + (xmax * crop_w / 1000)
                        
                        # Orijinal resme göre 0-1000 normalize koordinatlarına geri döndür (main.py'deki çizim mantığı için)
                        item['accidental_box_2d'] = [
                            abs_ymin * 1000 / orig_h,
                            abs_xmin * 1000 / orig_w,
                            abs_ymax * 1000 / orig_h,
                            abs_xmax * 1000 / orig_w
                        ]

            return results

        except Exception as e:
            print(f"!!! Gemini Analizi Sırasında Hata: {e}")
            return []

if __name__ == "__main__":
    analyzer = GeminiMusicAnalyzer()
    print("Gemini Analizörü başarıyla başlatıldı.")
