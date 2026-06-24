# Vektia Makine Öğrenimi ve Anti-Hile Sistemi

**Vektia**, çok oyunculu (multiplayer) oyunlarda veya yoğun etkileşim gerektiren sunucularda insan dışı hareketleri (Makrolar, Auto-Clicker'lar, Botlar ve Scriptler) tespit etmek için geliştirilmiş yüksek performanslı, katmanlı bir analiz motorudur.

---

## 🎯 Projenin Amacı
Geleneksel anti-hile (Anti-Cheat) yazılımları, arka planda çalışan programları tarar veya oyun dosyalarının değiştirilip değiştirilmediğini kontrol eder. Ancak donanım tabanlı makrolar (Mouse içine yazılan scriptler) veya dışarıdan gönderilen zararsız gibi görünen komutlar bu sistemleri kolayca atlatabilir. 

**Vektia**, oyuncunun "ne" kullandığına değil, **"nasıl"** oynadığına bakar. İnsan fizyolojisinin biyolojik sınırlarını (el titremesi, refleks hızı, ritim bozukluğu) referans alarak matematiksel ve istatistiksel metriklerle botları avlar.

---

## 🏗️ Mimari Yapı: Katmanlı Elek (Layered Filter) Sistemi

Vektia, işlemci ve bellek maliyetlerini en aza indirmek için 3 katmanlı bir elek sistemi kullanır. Her katman veriyi süzer, sadece gerçekten şüpheli veya karmaşık olan veriler yapay zekaya (Katman 3) ulaşır.

### Katman 1: RAM Korumalı Hızlı Tampon (Redis Sliding Window)
- Saniyede milyonlarca tıklama/hareket verisini (telemetri) karşılar.
- Verileri biriktirip yığın yapmak yerine, her oyuncunun sadece **son N hareketini (örneğin son 25 tıklama)** RAM'de tutar (Sliding Window).
- Redis Lua scriptleri kullanılarak inanılmaz hızlı çalışır ve inaktif oyuncuların verilerini otomatik silerek RAM'i şişirmez.

### Katman 2: İstatistiksel Filtre (Heuristics Engine)
- Kaydedilen son 25 hareketin zaman (timestamp) ve mekan (koordinat) farklarını alır.
- **Kesin kurallar (Hard Limits) ile %100 emin olunan botları anında tespit eder.** Eğer bu katmanda yakalanılırsa veri yapay zekaya gitmeden işlem bitirilir.
- Kullanılan Gelişmiş Algoritmalar:
  - **Mekansal Titreme (Spatial Jitter):** İnsan kasındaki fizyolojik titremeyi (tremor) kontrol eder. 25 tıklamada imleç 1 piksel bile hareket etmemişse ve ritmi iyiyse anında tespit eder.
  - **Gelişmiş Çoklu-Gecikmeli Otokorelasyon (Multi-Lag Autocorrelation):** Programlanmış sıralı döngüsel makroları yakalar (Örn: 10ms -> 20ms -> 50ms -> Başa dön).
  - **Değişim Katsayısı (CV) ve Range Ratio:** Yüksek hızlarda (Drag Click) insan ritminin bozulması zorunluluğunu ölçer. Çok hızlı ama çok stabil tıklayan makroları yakalar.
  - **Shannon Entropisi:** Olayların karmaşıklığını ölçer. Düşük entropi = Yazılımsal düzen.

### Katman 3: Yapay Zeka Anomali Tespiti (Isolation Forest)
- Katman 2'den geçen (bot olduğuna %100 emin olunamayan ama şüpheli olan) davranışlar yapay zeka modeline gönderilir.
- Makine öğrenimi algoritması (Isolation Forest), insan davranışlarının çoğunlukta olduğu büyük bir veri setiyle eğitilmiştir. 
- Standart sapma, entropi, çarpıklık (skewness) gibi metrikleri 6 boyutlu uzayda analiz ederek, insan kümesinin (cluster) dışında kalan sinsi makroları (örneğin rastgele gecikmeler eklenmiş akıllı makroları) ayıklar.

---

## 🚀 Öne Çıkan Özellikler

1. **Aksiyon Tipine Göre Tolerans (Action Type Discrimination):**
   - Vektia, klavyeden basılı tutulan bir "Yürüme (MOVE)" eylemi ile farenin sol tıkına basılan "Ateş Etme (CLICK)" eylemini birbirinden ayırır.
   - İşletim sisteminin mükemmel ritimde gönderdiği klavye tekrarlarında insanları bot olarak işaretlemez.

2. **Kör Noktasız (Blind Spot Free) Tespit:**
   - Bir oyuncu köşe tutarken (Angle Holding) faresini hiç hareket ettirmezse (0 piksel hareket), Vektia o kişinin ritmine bakarak onu gerçek oyuncu olarak sınıflandırır.
   - Ritim oyunları oynayan çok yetenekli bir oyuncu ritmik tıklasa da, kaslarındaki mikro gecikmeler Vektia'nın istatistiksel radarına takılır ve banlanmaktan kurtulur.

3. **Gerçek Zamanlı Karar Mekanizması:**
   - WebSockets üzerinden gelen canlı veri akışı (Stream) sayesinde tespit süresi milisaniyeler sürer.

---

## 📂 Dosya ve Dizin Yapısı

- `vektia/core/layer1_redis.py`: Sliding window veri toplama sistemi.
- `vektia/core/layer2_stats.py`: Bilimsel sınırlara dayanan istatistik motoru.
- `vektia/core/layer3_ml.py`: Makine öğrenimi modeli tahmini.
- `train_model.py`: Yapay zeka modelini önceden toplanmış oyuncu ve bot verileriyle eğitmek için kullanılan script.
- `public/demo.html`: Sistem testleri için hazırlanan, canlı makro avlama oyun simülasyonu.
