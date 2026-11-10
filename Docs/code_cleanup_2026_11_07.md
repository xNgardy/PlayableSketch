# Kod ve dosya temizliği — 7 Kasım 2026

Aktif proje kaynakları sadeleştirildi. Geçmiş deneylerin kaynak snapshot’ları, veri, etiket, model ve raporları değiştirilmedi.

## Kod

- 302 dosya incelendi; 298 dosya düzenlendi.
- 428 yorum ve 268 Python açıklama bloğu kaldırıldı.
- Komut satırı yardım metinleri kısa metinler olarak korundu.
- 12 kullanılmayan içe aktarma kaldırıldı.
- Python, C++/C#, JavaScript, HTML ve CSS tutarlı biçimde düzenlendi.
- Python AST, C++/C# belirteç ve önişlemci sınırları, JavaScript AST ve ham şablon değerleri doğrulandı.
- Çalıştırma satırları, include/pragma yönergeleri ve üçüncü taraf lisansları korundu.
- `.gitignore` dosyasına Python önbellekleri ve derleme artıkları için kurallar eklendi.

## Silinen dosyalar

1.827 üretilmiş dosya, toplam yaklaşık 7,09 GB mantıksal boyut. Dosya sistemi boş alanı yaklaşık 6,92 GB arttı.

- Paketleme Intermediate, StagedBuilds, Cooked, shader ve geçici klasörleri.
- Asıl uygulamayla 32 dosyası birebir aynı olan yinelenen paketleme uygulaması.
- Etkin olmayan eski corridor_addon eğitimine ait yeniden üretilebilir özellik/hedef önbelleği; manifesti temizlik kaydına alındı.
- Başarısız ve sonraki tamamlanmış değerlendirmeyle geçersiz kalan serialization_attempt çıktısı.
- Projeye ait Python bytecode ve önbellekler, DDC artıkları ve macOS klasör metaverileri.

Son tüm-veri eğitiminin önbelleği, modelleri ve değerlendirme kayıtları korundu. Python ortamları, DINO bağımlılıkları, asıl Mac uygulaması, Unreal Content ve kullanıcı iş/onay kayıtları silinmedi. Silinen yol listesi `deleted_artifacts.json` içindedir.

## Doğrulama

- 490/490 Python testi geçti.
- Silme sonrasında 50 yükleme/onay/dışa aktarma/DINO testi tekrar geçti.
- Aktif model Data_51 ve yeni aday Data_63 gerçek çıkarımları, temizlik öncesi bölge/kapı/bağlantı metriklerini birebir korudu.
- Veri ve model dahil 6.087 korunan dosyanın hash’i değişmedi.
- Asıl uygulamanın 32 dosyası değişmedi; başlatıcıların çalıştırma izinleri korundu.
- C++ yeniden derlenmedi: kaynak belirteçleri aynı ve mevcut paket uygulama korunmuş durumda.

## Geçmiş kayıtlar ve geri alma

Kaynak biçimi değiştiği için güncel dosya hash’leri geçmiş deney protokollerinden farklıdır. Geçmiş protokoller ve onların source_snapshot kopyaları özgün haliyle korundu; eski deney hash’leri güncel kodla eşleşiyormuş gibi değiştirilmedi.

Temizlik öncesi kaynak yedeği: `Saved/Maintenance/cleanup-2026-11-07/source_before.tar.gz`. Bu yedek, temizlikten önce var olan yerel kod değişikliklerini de içerir. Yalnızca yaklaşık 647 KB; toplu biçimlendirmeyi geri alabilmek için tutuldu.

Araçlar geçici klasöre kuruldu; proje Python ortamına veya uygulama bağımlılıklarına eklenmedi.
