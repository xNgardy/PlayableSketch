# Bağımsız sınır ve kapı deneyleri — 9 Kasım 2026

Canlı uygulama ve DINO ağırlıkları korunarak yeni deneyler yapıldı. Yeni modellerin test çizimleri kendi eğitimlerine katılmadı. Üretimdeki DINO tüm 70 özgün çizimle eğitildiği için eski DINO sonuçları bu tutulan test bölümüyle adil bir karşılaştırma değildir.

Eğitim: 49 özgün insan çizimi + 120 sentetik görüntü. Doğrulama: 7 insan + 24 sentetik. Test: 14 insan + 30 sentetik. Ayrıca eğitime alınmayan 20 birleşik U/L/S şekliyle stres testi yapıldı. Aynı kaynak farklı bölümlerde bulunmuyor; yazar bazında ayrım yok. İki WhatsApp fotoğrafı geliştirme örneğidir, bağımsız başarı kanıtı değildir.

YOLOv8n ve YOLO11n COCO başlangıcından 20 dönem; U-Net rastgele başlangıçtan 20 dönem; MobileNet V3 tabanlı Faster R-CNN, omurgası dondurularak 20 dönem eğitildi. Mask2Former Swin-Tiny, ADE20K başlangıcından, omurgası dondurularak 5 dönem yalnızca 120 yoğun etiketli sentetik görüntüyle eğitildi. Mask2Former için veri ve güncelleme bütçesi farklıdır; bu pilot mimarilerin genel sıralaması olarak okunamaz.

Kapı kutuları yaklaşık elle çizilmiş boşluk uçlarından türetildi; ayrıca doğrulanmış nesne kutuları değildir. Kapı eşleştirmesi IoU ≥ 0.5 ve birebir en iyi atama ile yapılır. Güven eşikleri yalnız doğrulamada seçilir. Duvar/kapı maskeleri birleştirilir, kapılar geçici kapatılır ve dış arka planı dışlayan bağlı alanlar oda sayılır. Arada ayırıcı olmayan alanlar tek odadır. Açık geçişlerle bağlanan eski oda/koridor referansları birleştirildi.

## İnsan çizimleri: tutulan test

14 test çiziminde toplam 16 kapı etiketi var. Oda referansı olmayan iki görüntü oda değerlendirmesinden çıkarıldı; oda sayısı başarısının paydası 12. Küçük ve yaklaşık etiketli bir testtir.

| Akış | Kapı P % | Kapı R % | Kapı F1 % | Oda F1 % | Doğru oda sayısı |
| --- | ---: | ---: | ---: | ---: | ---: |
| CV, kapı ayırmadan | 0.0 | 0.0 | 0.0 | 7.1 | 3/12 |
| CV duvar + YOLOv8n | 63.2 | 75.0 | 68.6 | 13.8 | 6/12 |
| CV duvar + YOLO11n | 90.9 | 62.5 | 74.1 | 14.6 | 4/12 |
| U-Net duvar + U-Net kapı | 0.9 | 18.8 | 1.7 | 36.8 | 1/12 |
| U-Net duvar + YOLO11n | 90.9 | 62.5 | 74.1 | 60.0 | 4/12 |
| Mask2Former duvar + kapı | 0.0 | 0.0 | 0.0 | 20.0 | 0/12 |
| Mask2Former duvar + YOLO11n | 90.9 | 62.5 | 74.1 | 36.4 | 1/12 |
| CV duvar + Faster R-CNN | 33.3 | 37.5 | 35.3 | 13.7 | 6/12 |
| U-Net duvar + Faster R-CNN | 33.3 | 37.5 | 35.3 | 65.1 | 5/12 |

Oda F1, referans oda çokgenleriyle alan IoU ≥ 0.5 eşleşmesini ölçer. Yalnız doğru sayıyı bulmak, doğru konum/şekli bulmak anlamına gelmez. CV kontrolünde kapı dedektörü kullanılmaz; bu bir ayırma kontrolüdür.

## Yeni fotoğraflar

| Akış | L: oda/kapı (beklenen 4/3) | U: oda/kapı (beklenen 2/1) |
| --- | ---: | ---: |
| CV, kapı ayırmadan | 1/0 | 1/0 |
| CV duvar + YOLOv8n | 1/0 | 2/1 |
| CV duvar + YOLO11n | 1/0 | 1/0 |
| U-Net duvar + U-Net kapı | 2/14 | 1/6 |
| U-Net duvar + YOLO11n | 1/0 | 0/0 |
| Mask2Former duvar + kapı | 0/0 | 0/0 |
| Mask2Former duvar + YOLO11n | 0/0 | 0/0 |
| CV duvar + Faster R-CNN | 1/0 | 1/0 |
| U-Net duvar + Faster R-CNN | 1/0 | 0/0 |

## Ayrı sentetik test

| Akış | Kapı F1 % | Oda F1 % | Doğru oda sayısı |
| --- | ---: | ---: | ---: |
| CV, kapı ayırmadan | 0.0 | 28.0 | 4/30 |
| CV duvar + YOLOv8n | 100.0 | 96.6 | 25/30 |
| CV duvar + YOLO11n | 100.0 | 96.6 | 25/30 |
| U-Net duvar + U-Net kapı | 22.3 | 45.5 | 10/30 |
| U-Net duvar + YOLO11n | 100.0 | 96.6 | 25/30 |
| Mask2Former duvar + kapı | 80.9 | 90.6 | 20/30 |
| Mask2Former duvar + YOLO11n | 100.0 | 96.6 | 25/30 |
| CV duvar + Faster R-CNN | 100.0 | 96.6 | 25/30 |
| U-Net duvar + Faster R-CNN | 100.0 | 96.6 | 25/30 |

## Eğitim dışı birleşik şekiller: stres testi

| Akış | Kapı F1 % | Oda F1 % | Doğru oda sayısı |
| --- | ---: | ---: | ---: |
| CV, kapı ayırmadan | 0.0 | 71.4 | 4/20 |
| CV duvar + YOLOv8n | 82.1 | 92.3 | 14/20 |
| CV duvar + YOLO11n | 81.5 | 92.5 | 15/20 |
| U-Net duvar + U-Net kapı | 0.0 | 71.4 | 4/20 |
| U-Net duvar + YOLO11n | 81.5 | 92.5 | 15/20 |
| Mask2Former duvar + kapı | 0.0 | 73.7 | 5/20 |
| Mask2Former duvar + YOLO11n | 81.5 | 90.9 | 14/20 |
| CV duvar + Faster R-CNN | 30.8 | 80.6 | 10/20 |
| U-Net duvar + Faster R-CNN | 30.8 | 80.6 | 10/20 |

## Yorum ve sonraki adım

Bu pilotta insan testindeki en yüksek kapı F1 YOLO11n ile %74,1 oldu (10 doğru, 1 fazla, 6 kaçan kapı). YOLOv8n %68,6 verdi (12 doğru, 7 fazla, 4 kaçan). Gönderilen U fotoğrafında doğru 2 oda/1 kapı sonucunu veren bağımsız akış CV duvar + YOLOv8n oldu; görsel sınırlar da kontrol edildi. Buna karşılık L fotoğrafındaki üç küçük kapıyı yeni dedektörlerin hepsi kaçırdı. Bu örnekler modele ve görüntü ölçeğine bağlı hata bulunduğunu gösterir; yalnız model adını değiştirmenin yeterli olduğunu desteklemez.

U-Net duvar maskesi, insan testindeki bilinen yaklaşık etiketli piksellerde %91,7 F1 verdi. Bu yoğun insan maskesiyle ölçülmüş bir F1 değildir. Buna rağmen kapı kapatma maskesinden nesne çıkarımı %1,7 kapı F1 ile kararsızdı. Aynı YOLO11n kapıları kullanıldığında oda çokgeni F1, CV duvarla %14,6 iken U-Net duvarla %60,0 oldu; doğru oda sayısı ikisinde de 4/12 kaldı. Piksel başarısı ile doğru oda topolojisi farklı ölçülerdir.

Kapı tespiti ile oda topolojisi ayrı değerlendirilmelidir. Kapı F1 yüksekken oda sayısının düşük kalması, dedektörden sonra duvar maskesi bütünlüğü, kapının duvara oturtulması veya çözünürlük sorunu olduğuna işaret eder. Bu deneyler DINO’nun patch yapısının tek başına hata sebebi olduğunu kanıtlamaz. U-Net ve Mask2Former için daha uzun ve eşit koşullu eğitim, yoğun insan maskeleri ve yeni yazarlardan ayrılmış test gerekir. Hiçbir deney modeli canlı sisteme atanmadı.

Duvar segmentasyonu için [CubiCasa5K](https://github.com/CubiCasa/CubiCasa5k) ve mimari semboller için [FloorPlanCAD](https://floorplancad.github.io/) başlangıç veri kaynakları olabilir. Çentik biçimindeki kapı işaretlerini aynı biçimde etiketleyen kendi verimiz yine gerekir; bu dış veri kümeleri bu deneye indirilmedi veya dahil edilmedi.

Model kaynakları: [YOLO11](https://docs.ultralytics.com/models/yolo11/), [Faster R-CNN](https://docs.pytorch.org/vision/stable/models/faster_rcnn.html), [Mask2Former](https://huggingface.co/docs/transformers/model_doc/mask2former).

Yeniden çalıştırma kaynakları: `Scripts/independent_boundary_experiment.py`, `Scripts/independent_boundary_stress_data.py`, `Scripts/independent_mask2former_experiment.py`. Protokoller, eğitim geçmişleri, seçilen ağırlıklar, görüntü başına sonuçlar ve ham rapor bu klasördedir.
