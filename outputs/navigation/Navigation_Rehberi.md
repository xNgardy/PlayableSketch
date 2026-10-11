# PlayableSketch — Navigation Grid

Bu aşama, üretilmiş levelde belirli boyuttaki bir karakterin Start'tan Goal'a yürüyüp yürüyemediğini hesaplar. Input Graph'ta Connection bulunması tek başına geçiş kanıtı değildir. FloorPlan ile gerçekten üretilmiş Wall/Lintel descriptorları birlikte kullanılır.

## Eklenen davranış

1. FloorPlan boundslarından sınırlı bir grid oluşturulur. Origin otomatik hesaplanır; hücre merkezleri layout gridine hizalanır. Cell size için mevcut `GridStepCm` kullanılır. Varsayılan üst sınır `NavigationMaxCells=250000`; mutlak üst sınır 1000000 hücredir. Hesaplama ayrıca 50000000 işlem bütçesiyle sınırlıdır.
2. Oda ve koridor floor alanlarının **birleşimi** değerlendirilir. Her dikdörtgeni ayrı ayrı daraltmak, oda-koridor birleşiminde sahte engel üretebilirdi. Bunun yerine hücrenin ihtiyaç duyduğu destek alanının tamamının birleşim içinde kalması aranır.
3. Destek alanının yarı genişliği `PawnRadiusCm + ClearanceCm + GridStepCm/2` olur. Axis-aligned kare kullanılır; dairesel kapsülden daha muhafazakârdır. Duvar footprinti bu alanla kesişiyorsa hücre blocked olur. Hücrenin bütün alanını hesaba katmak ince bir duvarın iki örnek nokta arasında kaybolmasını önler.
4. Duvarın düşey aralığı ayak seviyesi ile `PawnHeightCm + ClearanceCm` arasına giriyorsa engeldir. Lintel yeterince yukarıdaysa geçişi kapatmaz; alçaksa kapatır. Aynı mantık corridor cap için de çalışır.
5. Start/Goal için oda merkezine en yakın güvenli hücre seçilir. Merkez engelliyse başka hücre aranır. Odada hiç güvenli hücre yoksa açık durum mesajı ve unreachable sonucu üretilir.
6. Sağ, yukarı, sol, aşağı komşularla BFS çalışır. Diagonal hareket yoktur. En kısa grid yolu `adım sayısı × hücre boyutu` olarak ölçülür; gerçek dünyadaki en kısa çapraz yol olduğu iddia edilmez.
7. Başarılı Full/Local geometry publish işleminden sonra navigation otomatik tekrar hesaplanır. Navigation ve validation hâlâ globaldir; geometri registry ile yerel güncellenmeye devam eder. Başarısız/stale preview, Clear veya source değişiminde eski path ve navigation snapshotı temizlenir.

Navigation sonucu “unreachable” olabilir ve bu, geometry build hatası değildir. Geometri geçerlidir fakat seçilen karakter/grid modeli geçiş bulamıyor olabilir. Sonuç Details panelinde ayrıca gösterilir.

## Beş metrik

| Metrik | Hesap |
|---|---|
| Reachable | Start temsilci hücresinden Goal temsilci hücresine grid yolu var mı? |
| RouteLength | En kısa BFS yolunun adım sayısı × cell size. Yol yoksa UI'da NA, JSON'da null. |
| UnreachableRooms | Start'tan temsilci hücresine ulaşılamayan veya güvenli hücresi bulunmayan Room ID'leri. |
| DeadEnds | Gerçekten geçilebilen Connection sayısı bir olan odalar; Start ve Goal hariç. |
| AlternativeRoute | Temel rotada kullanılan her Connection tek tek kapatılır. Her kapatmada Goal hâlâ erişilebilir olmalı. |

Bir Connection'ı fiziksel saymak için iki uç oda ve o koridorun floor alanıyla sınırlı hücreler üzerinde ayrı BFS yapılır. Global walkability zaten duvar, lintel ve karakter clearance'ını içerir. Başka koridordan dolanmak o Connection'ı yanlışlıkla geçilebilir saydırmaz.

Alternatif rota testinde yalnız bir graph edge'i kaldırılmaz: ilgili Connection'ın **iki kapı portalı gridde kapatılır**, karakter/hücre payıyla genişletilir ve tekrar BFS çalışır. Böylece kapanmış açıklıktan gridin geçmeye devam etmesi önlenir. Kapamalar bağımsızdır; aynı anda bütün rota kapıları kapatılmaz.

## Editor'de kullanım

1. Actoru seç, GraphAsset ata ve geçerli geometry üretmek için `Generate Layout` veya `Rebuild Geometry` çalıştır.
2. `PlayableSketch | Navigation` altında `Navigation Report` sonucunu oku. Reachable ise yeşil path otomatik görünür. Viewport debug çizimleri için Realtime açık olmalı.
3. `Show Navigation Grid` ile cyan walkable hücreleri göster. `Show Blocked Navigation Cells` ile red blocked hücreleri de göster. Görselleştirme frame başına en fazla yaklaşık 5000 örnek hücre çizer; büyük gridde örnekleme yapar. Analiz sonucu bundan etkilenmez.
4. `PawnRadiusCm`, `PawnHeightCm`, `ClearanceCm` alanları mevcut Validation kategorisindedir; navigation da aynı karakter ölçülerini kullanır. Yeni, çelişen agent ayarları eklenmedi.
5. `Analyze Navigation` mevcut güncel geometriyi yeniden analiz eder. Eski `Test Floor Path` düğmesi de artık bu analizi çağırır. Önceki floor-only navigation yardımcıları silinmedi; yeni ana akış onları kullanmaz.
6. `Export Navigation Report`, mevcut tasarım için `Saved/Navigation/NavigationReport.json` yazar. `Navigation Export Path` tam dosya yolunu gösterir. Dosya aynı isimle yenilenir.
7. `Run Navigation Examples`, beş sabit yerleşimli örnek çalıştırıp `Saved/Navigation/NavigationExamples.json` yazar. Mevcut GraphAsset ve level tasarımını değiştirmez. Örneklerin seed alanı kayıtlıdır; yerleşimler seed aramasıyla üretilmiş deney gibi sunulmaz, `fixed_layout_fixture=true` ile işaretlenir.

## Beş örnek

| Örnek | Beklenen |
|---|---|
| ThreeRooms | Üç oda zinciri, Goal erişilebilir; rota 2800 cm, alternatif false. |
| ChainWithBranch | Goal erişilebilir; Start/Goal dışında bir fiziksel çıkmaz oda. |
| Ring | Dört fiziksel bağlantı; her rota Connection'ı kapatıldığında dolaşılabilir, alternatif true. |
| BlockedDoor | Bağlantı verisi var fakat açıklığı solid cap kapatıyor; Goal erişilemez, rota null. |
| LargeAgent | Aynı açıklıklardan daha geniş karakter geçemiyor; Goal erişilemez. |

JSON ayrıca Room/Connection sayıları, cell size, agent ölçüleri, grid origin/dimensions, walkable/visited sayıları, fiziksel/rota Connection ID'leri, durum ve süreleri içerir. `build_ms`, `search_ms`, `metrics_ms`, `total_ms` ayrı kaydedilir. Rebuild raporundaki `NavigationMs` navigation analizini; `TotalMs` geometri ve navigation dahil toplam çağrıyı kapsar. Render/GPU/frame tamamlama süresi bu ölçümlere dahil değildir.

## Değişen dosyalar

Mevcut dosyalarda yalnız gerekli entegrasyon yapıldı:

- `PlayableSketchLevelActor.h`: navigation düğmeleri, görünüm/report alanları, snapshot ve yardımcı metodlar.
- `PlayableSketchLevelActor.cpp`: başarılı publish sonrası analiz, stale sonuç temizliği, path/grid çizimi, JSON dışa aktarma.
- `PlayableSketch.Build.cs`: serializer için private `Json` dependency. Graph, layout, routing, wall geometry, registry veya validation algoritmaları değiştirilmedi.

Yeni dosyalar:

- `Public/Navigation/PlayableSketchNavigation.h`
- `Private/Navigation/PlayableSketchNavigation.cpp`
- `Public/Navigation/PlayableSketchNavigationExamples.h`
- `Private/Navigation/PlayableSketchNavigationExamples.cpp`
- `Private/Validation/Tests/PlayableSketchNavigationTests.cpp`

## Testler

`PlayableSketch.Navigation.GridAndMetrics`: beş örnek; BFS determinismi ve array sırası; dört komşu; ince cap; yüksek/alçak lintel; büyük/yüksek karakter; engelli merkezden yakın hücre seçimi; tamamen kapalı Goal; floor birleşimi ve boşluk; input/grid/iş bütçesi sınırları; JSON'un diske yazılıp tekrar parse edilmesi ve null değer kontrolü.

`PlayableSketch.Navigation.ActorLifecycle`: geometry publish sonrası otomatik analiz; Local Rebuild sonrası yenilenme; gereksiz component oluşturulmaması; dar kapıda eski yeşil yolun kaldırılması; güncel JSON export; Clear sonrası navigation temizliği.

Önceki `PlayableSketch.Geometry.LocalRebuild` ve `PlayableSketch.Authoring.Validation` testleri de regresyon için çalıştırılır. Test adlarında gün numarası bulunmaz.

## Sınırlar ve manuel kontrol

Bu model tek kat, yatay zemin ve sabit agent boyutuyla normal yürümeyi kapsar. Jump, stairs, A*, Recast/NavMesh, AI pawn hareketi veya gerçek kapsül sweep simülasyonu eklenmedi. Pitch/roll veya unit olmayan Actor scale için modelin yanlış karakter ölçüsü kullanmaması amacıyla navigation açık mesajla devre dışı kalır; translate/yaw desteklenir ve geometry korunur.

Kare footprint ve yarım hücre payı nedeniyle dar/diagonal köşeli veya gridle hizalanmayan bazı geçişler güvenli biçimde kapalı sayılabilir. Grid çözünürlüğünü küçültmek hassasiyeti artırır ama hücre/iş miktarını büyütür. Özellikle geçiş genişliği tam sınırdaysa “yol yok” sonucu fiziksel dünyada kesinlikle hiçbir yol olmadığı anlamına gelmez. Ama dar geçişi yanlışlıkla açık saymamak hedeflenir.

Kendi sahnende farklı karakter ölçüleriyle test et. Gerçek Pawn ile kapıdan geçme, duvarda durma ve actor transformlarını görsel olarak kontrol et. Otomasyon matematiksel model ve lifecycle'ı doğrular; gerçek oynanış testinin yerine geçmez.

## Doğrulama sonucu

UE 5.7.4 Development Editor / Win64 derlemesi başarılı. Yukarıdaki iki navigation testiyle mevcut Local Rebuild ve Authoring Validation testlerinin dördü de başarılı, test hatası yok. Testler NullRHI ile çalıştırıldı. Beş örneğin JSON dosyası diskte yeniden açılıp parse edildi; sonuçlar beklenen değerlerle eşleşti.

Kaynak kapsamı başlangıç dosya hashleriyle kontrol edildi: üç mevcut dosya değişti, beş yeni kaynak dosyası eklendi. Config, Content ve diğer mevcut Source dosyaları değişmedi. Test raporu `work/navigation-integration/test-report/index.json`, derleme ve test logları aynı çalışma klasöründedir.
