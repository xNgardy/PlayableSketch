# Son modelin projede etkinleştirilmesi — 7 Kasım 2026

Kullanıcının seçimiyle altı tur tüm-veri eğitiminin son modeli, yerel çalışma alanı ve paket runtime başlatıcılarının varsayılanı yapıldı.

- Dağıtım ağırlığı: `SketchPipeline/shape_authoring/models/shape-dinov2-all-data-v1.pt`
- SHA256: `efe0b245734472c4198c2ab525e9175e7e0f4268d87c99ef2043582613344eb6`
- Ortak seçim dosyası: `SketchPipeline/shape_authoring/dinov2-candidate.lock.json`
- Her iki başlatıcı aynı model, refined-full profil ve mürekkep normalizasyonu ayarını kullanır.
- Açık servis yeniden başlatıldı ve yeni model ayarı doğrulandı. Devam eden iş yoktu; altı mevcut kayıt korundu.
- Eski modellerin tamamı ve eğitim checkpoint’leri korundu.
- Yeni yüklemeler yeni modelle analiz edilir. Önceden kaydedilmiş sonuçlar ve onaylı planlar geçmiş model bilgileriyle korunur; sessizce yeniden analiz edilmez.
- Farklı modelle çalışan bir servis başlatıcı tarafından artık sessizce yeniden kullanılmaz.
- 494 Python testi geçti; ayrı geçici localhost sunucusunda gerçek yükleme/worker çıkarımı yeni model hash’iyle doğrulandı. Kullanıcı çalışma alanına test işi eklenmedi.
- Kullanıcı onayı, plan düzenleme ve dışa aktarma akışı korunur. Sayısal OCR çağrılmaz.

## Kullanım

1. `Start Sketch Workspace.command` aç veya açık çalışma alanı sekmesini yenile: http://127.0.0.1:8772/.
2. Çizimini yükle, planı kontrol et, Playable level ve Start/Goal seçip onayla ve dışa aktar.
3. `Start PlayableSketch.command` aç; Open latest plan ile oyuna geç.

## Değerlendirme kaydı

Bu sürüm yerel projenin seçilmiş son modelidir. Tüm eğitim verisinde ölçülmüştür; bağımsız yeni-yazar doğrulaması yapılmış gibi işaretlenmedi. Önceki değerlendirme raporları özgün tarihsel durumlarıyla korundu. Tüm-veri eğitiminde eski 50 özgün çizimin bağlantı F1 kaybı dahil sonuçlar `Docs/all_data_training_2026_11_07.md` içinde yer alır.

Model etkinleştirme kontrolleri ve önceki başlatıcı/ayar yedekleri `Saved/Maintenance/model-promotion-2026-11-07` altındadır.
