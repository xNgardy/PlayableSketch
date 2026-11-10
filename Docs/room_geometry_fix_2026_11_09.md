# Oda geometrisi düzeltmesi — 9 Kasım 2026

Gönderilen fotoğrafta önceki sonuç 5 dikdörtgen alan (3 oda, 2 koridor) içeriyordu. Güncel üretim akışı aynı özgün fotoğraftan 4 oda ve 3 kapı çıkarıyor. İkinci oda altı köşeli L geometrisini koruyor; boş kağıttaki fazladan oda kaldırıldı ve sağdaki alan oda olarak işlendi.

Tüm yeni otomatik öneriler tek oda türüne dönüştürülüyor. Arayüzde koridor ekleme ve tür seçimi kaldırıldı. Eski veri etiketleri ve kayıtlar korunuyor.

Yeni geometri adımı görüntüyü 1024 piksele kadar inceleyerek çizgiyle çevrili alanları ve kapılardaki eşleşen kısa çizgileri kullanıyor. Sınır desteği, şekil örtüşmesi, çakışma ve kapı bağlantısı kontrolleri geçerse bu öneri kullanılıyor; eksik veya belirsiz çevrelerde mevcut model önerileri korunuyor. Bu kontrolün her yeni çizimde doğru sonuç vereceği gösterilmiş değildir.

L odası düzenleyicide ve ölçülendirmede tek çokgen olarak saklanır. Paketlenmiş oyun motorunun mevcut dikdörtgen zemin formatı için L zemini iki bitişik parçaya ayrılır. Aradaki bağlantı tam genişlikte açık geçiştir; arayüz bu parçaları tek oda olarak gösterir. Bu fotoğrafın dışa aktarma önizlemesi 4 mantıksal oda için 5 zemin parçası içerir.

Doğrulama: 501 test içeren tam test paketi geçti. Daha sonra eklenen döndürme ve kaydetme testleriyle birlikte 53 ilgili test tekrar geçti. JavaScript sözdizimi denetimi ve tarayıcıdaki çizim/plan görünümü kontrol edildi. Fotoğrafın ölçülendirmesi hazır; 2B oyuncu açıklığı kontrolü başarılı. Unreal içindeki gerçek oynanış bu düzeltme sırasında çalıştırılmadı.

Model ağırlıkları değişmedi. Önceki precision/recall/F1 raporları eski çözümleme akışına aittir; yeni akış için yeniden hesaplanmadı. Fotoğraf eğitim verisine eklenmedi. Bu örnek genel başarı oranı olarak yorumlanmamalıdır.

Eski iki fotoğraf analizi korunarak `shape_fe36f14ed7084d9d86311dd98c94e289` kimliğiyle yeni analiz açıldı. Kullanıcı onayı veya dışa aktarım yapılmadı.

Kanıtlar: `Saved/ShapeFirst/room_geometry_fix_2026_11_09/verification.json`, `full-tests.log`, `final-targeted-tests.log`, `plan-preview.png`.
