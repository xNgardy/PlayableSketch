# El çizimi plan algılama: araştırma ve yöntem önerisi

Araştırma tarihi: 4 Kasım 2026. Makaleler, yazarların depoları ve yayımladıkları
lisanslar incelendi. Bu çalışma yeni modelleri bizim görüntülerimizde çalıştırmış
bir benchmark değildir. Aşağıdaki yöntem seçimi kaynaklar ve yerel hata analizi
üzerinden mühendislik önerisidir; garantili doğruluk iddiası yoktur.

Öneri: **ImageNet ön eğitimli ResNet34 encoder + çok görevli U-Net decoder;
oda instance'ları, mantıksal sınırlar ve kapı keypoint'leri; ardından kısıtlı graph
oluşturma ve insan düzeltmesi.** Raster2Seq hazır ağırlıkları güçlü bir araştırma
karşılaştırması olabilir; doğrudan ürün varsayılanı olarak seçilmemeli.

## Başkaları nasıl yaklaşmış?

| Çalışma | Kullanılan model/pipeline | Bizim için değerlendirme |
| --- | --- | --- |
| Raster-to-Vector, ICCV 2017 | CNN ile junction/door endpoint ve semantik kanıt; integer programming ile çizgi ve kutuların tutarlı vektör plana birleştirilmesi | Algılama ile topoloji kontrolünü ayırma fikri uygun; araştırma skorları bizim serbest çizim dağılımımızı temsil etmiyor |
| CubiCasa5K, 2019 | Raster-to-Vector tabanlı çok görevli model; segmentation ve heatmap etiketleri; 5.000 plan | Güçlü bir plan parsing referansı. Bizim tick kapı dilimize hazır uyum kanıtı yok |
| DeepFloorplan, ICCV 2019 | Ortak encoder, sınır/oda görevleri ve room-boundary-guided attention | Oda tahmininin sınır kanıtını kullanması eksik region sorunumuzla doğrudan ilgili |
| Structure Descriptors-Guided Hand-drawn Floor Plan Reconstruction, IROS 2024 | Öğrenilmiş yapısal descriptor tanıma; descriptor bağlantıları, koordinat düzeltmesi, door/window reconstruction | Doğrudan kağıt ve elektronik el çizimlerini ele alıyor. Erişilebilen yazar özetinden bu bileşenler doğrulandı; tam metin fetch başarısız olduğundan belirli backbone/ağırlık/lisans varsayılmadı |
| RoomFormer, CVPR 2023; Floor-SP, ICCV 2019 | RoomFormer room/corner query'leriyle polygon; Floor-SP room-wise shortest path optimizasyonu | Asıl girdileri 3D/RGB-D taramalardan türetilen haritalar. Yöntem fikirleri yararlı, mevcut ağırlıkları el çizimine takıp aynı sonuç beklemek uygun değil |
| Raster2Seq, SIGGRAPH 2026 | Görüntü özelliklerinden autoregressive, etiketli polygon dizisi; room/door/window geometri ve semantiği | Doğrudan raster görüntüye uygulanabilen güçlü aday. Özel CUDA bileşenleri ve ayrı checkpoint lisansı var |
| FloorPlanFormer, AAAI 2026 | Swin backbone, pixel decoder; dış sınır ve iç oda maskeleri arasında refinement | İlgili bir yeni mimari. Resmî depo train verisinin henüz paylaşılacağını söylüyor; hazır kurulumun bütün parçaları doğrulanmış değil |
| Sketch2BIM, 2025 arXiv / 2026 journal kaydı | GPT-5 ile sketch→JSON, insan geri bildirimi, schema/topology validation, ardından Revit script üretimi | İnsan düzeltmesiyle çalışan alternatif. Deney yalnızca 10 planda; geri bildirim sonrası doğruluk otomatik ilk-pass başarısıyla karıştırılmamalı |
| floorplan-digitizer projesi | YOLOv8 wall/dimension detection, ResNet18 digit OCR, OpenCV ve DXF | 63 kişisel el çizimiyle uygulama örneği. Sayı okumaya dayanan yeniden kurma ve oda/kapı graph benchmark'ı eksikliği nedeniyle ana yöntemimiz değil |

Tablodaki yöntemlerin birincil kaynakları:

- [Raster-to-Vector: yazar makalesi](https://art-programmer.github.io/floorplan-transformation/paper.pdf)
- [CubiCasa5K: resmî depo](https://github.com/CubiCasa/CubiCasa5k)
- [DeepFloorplan: makale](https://arxiv.org/abs/1908.11025) ve [yazar deposu](https://github.com/zlzeng/DeepFloorplan)
- [El çizimi descriptor yaklaşımı: yazar PDF'si / indekslenmiş özet](https://aipu-seu.cn/upload/file/20240701/6385544406759769693941654.pdf)
- [RoomFormer](https://github.com/ywyue/RoomFormer) ve [Floor-SP](https://github.com/woodfrog/floor-sp)
- [Raster2Seq: yazar deposu](https://github.com/Cornell-VAILab/Raster2Seq)
- [FloorPlanFormer: yayın](https://ojs.aaai.org/index.php/AAAI/article/view/37625) ve [resmî depo](https://github.com/LTayfaker/FloorPlanFormer)
- [Sketch2BIM: makale](https://arxiv.org/abs/2510.20838)
- [floorplan-digitizer: geliştiricinin deposu](https://github.com/wojtek-smyczek/floorplan-digitizer)

## Neden mevcut modele biraz daha eğitim vermek yeterli bir plan değil?

[Yerel deneyde](step02_human_adaptation_2026_11_04.md) 11 eksik opening'in 8'i
eksik region'a bağlıydı. Son uyarlama yalnızca tick/junction head'lerini değiştirdi.
Ayrı 9 planda 2/18 opening bulundu; tam sentetik kontrol geriledi. Konumu bulunan
bir açıklığın doğru iki region'a bağlanması da ayrıca sorunlu.

Mevcut `ShapeUNet` ön eğitimsiz küçük bir ağ. Sentetik generator altı layout
ailesi kullanıyor; 384 eğitim görünümü 96 parent'tan geliyor. Layout/topoloji ve
kalem/fotoğraf çeşitliliği gerçek kullanıcı dağılımını kapsadığı gösterilmiş değil.
Bu yüzden yalnızca decoder eşiği ve marker head'iyle ilerlemek yerine temsil,
veri ve graph seçimini birlikte ele almak daha makul. Bu nedensel açıklama bir
hipotezdir; kontrollü karşılaştırmayla test edilmelidir.

## Önerdiğim uygulama pipeline'ı

1. **Girdi ve ölçek:** Orijinal görüntüyü tut. Geometri dönüşümlerini kaydet.
   Tam görüntüde genel plan bağlamını, gerektiğinde yüksek çözünürlüklü örtüşen
   crop'larda küçük tick'leri işle. Crop'lar birleştirilirken tek koordinat frame'i
   kullan; padding bölgelerini model kanıtı sayma.
2. **Ön eğitimli görsel encoder:** İlk aday `ResNet34 + U-Net`. ImageNet ağırlıkları
   floorplan uzmanı değildir; yalnızca öğrenilmiş görsel başlangıç sağlar. SMP bu
   kombinasyonu doğrudan destekliyor. Başlangıçta encoder'ı koruyup yeni decoder'ı
   eğit; validation sonucuna göre üst encoder katmanlarını düşük LR ile aç.
3. **Ayrı ama ortak özellik kullanan çıktılar:** Görünen wall ink; room/corridor
   interior; oda instance ayırımı için center/offset veya mesafe çıktıları;
   mantıksal room boundary; junction ve paired door endpoint heatmap'leri;
   açık corridor interface'i. Bu başlıkların tam birleşimi bizim tasarım önerimizdir,
   tek bir makalenin aynen uygulanması değildir. Instance çıktısı aynı tipte yan
   yana iki odanın tek maske olarak birleşmesini önlemeyi hedefler.
4. **Mantıksal sınır ve fiziksel boşluğu ayır:** Kapının olduğu yerde oda sınırı
   devam eder, fiziksel wall ink'i kesilir. Sadece açık mürekkep konturunu flood-fill
   ederek oda bulmaya dayanma. Mantıksal sınır önerisi görüntü kanıtına bağlı olsun;
   çizgi kırığını kapıya veya yeni odaya otomatik yükseltme.
5. **Topoloji oluştur:** Önce oda/corridor instance adaylarını ve shared boundary'yi
   üret. Door adayını bu boundary üzerinde iki endpoint ve gerçek gap kanıtıyla
   değerlendir. Atamayı yalnızca en yakın iki kutuyu seçerek yapma; duvar desteği,
   endpoint uyumu, iki taraftaki region ve duplicate cezalarını birlikte kullan.
   Önce küçük bir kısıtlı arama/optimizasyon yeterli; GNN eklemek ilk zorunluluk değil.
6. **Contract ve düzeltme:** Çakışan region, yanlış owner ve duplicate opening'i
   doğrula. Belirsiz olanı kullanıcıya göster. Mevcut shape-authoring contract,
   pending acceptance ve manual editing kullanılır; yeni numeric OCR gerekmez.

[SMP'nin resmî örneği](https://github.com/qubvel-org/segmentation_models.pytorch)
ResNet34 encoder, ImageNet ağırlığı ve U-Net kombinasyonunu destekliyor.
[Torchvision](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.resnet34.html)
da ResNet34 ImageNet checkpoint'ini belgeliyor. Bu kaynaklar modelin bizim
çizimlerimizde daha iyi sonuç vereceğini kanıtlamaz. Avantajı küçük ağımızdan daha
güçlü ve standart bir başlangıçla aynı yerel PyTorch iş akışında denenebilmesi.
Mac/MPS hız ve bellek kullanımı ayrıca ölçülmeli; bu araştırmada ölçülmedi.

## Eğitim verisi ve değerlendirme değişikliği

Bizim kapı convention'ı **gap + iki dik tick**. Klasik mimari planlardaki kapı yayı
ve sembollerle aynı değildir. Hazır CAD modelinin çıktı sınıfını yalnızca yeniden
adlandırmak bu farkı çözmez; bizim sembol dilimizle etiketlenmiş veri gerekir.

- Sentetik layout çeşitliliğini artır: farklı oda sayısı ve oranları, dar corridors,
  branching/cycles, staggered shared walls, bir boundary'de birden fazla door.
- Kalem stilini çeşitlendir: overshoot/undershoot, basınç, farklı tick uzunluğu,
  yakın yazı, grid, gölge, perspektif ve JPEG bozulması. Etiketleri bütün geometrik
  dönüşümlerle birlikte taşı; yalnızca daha çok aynı seed varyantı üretmekle yetinme.
- Gerçek çizimlerde room instance, intended boundary ve door→iki region ilişkisini
  gözden geçir. Yaklaşık etiketlerin belirsizlik maskelerini koru.
- Yeni yazar ve yeni parent plan gruplarından ayrı kör test kur. Önceki 9 plan artık
  yeni kör test değildir. Eğitim, validation ve test türevleri parent düzeyinde ayrılır.
- Checkpoint seçimi yalnızca validation: instance region recall, doğru owner'la
  birlikte opening F1, false/duplicate connection ve tam graph doğruluğu. Pixel IoU
  veya opening konumu tek başına başarı sayılmamalı. Düzeltme süresini de ölç.

Bu adımlar için belirli bir veri adedinin yeterli olacağı kanıtlanmış değil;
etiketleme bütçesi öğrenme eğrisi ve hata türlerine göre artırılmalı.

## Diğer adayların yeri ve kullanım koşulları

**Raster2Seq:** Hazır bir modelle doğrudan polygon çıktısı almak açısından önemli
karşılaştırma. Önce bizim gap/tick örneklerinde ölçülmeli; CAD benchmark skoru
serbest el çizimi skoru değildir. Depo Linux/CUDA, derlenen deformable-attention ve
rasterization modülleri kullanıyor. Mac'e doğrudan uygunluğu gösterilmiş değil.
Bu maliyet nedeniyle ilk yerel uygulama tercihim hafif CNN yaklaşımı.

**VLM:** Sketch2BIM, görsel→JSON→insan düzeltmesi→doğrulama ayrımının bir örneği.
Bizde istenirse ikinci görüş veya eksik region adayı üretmek için değerlendirilebilir.
Piksel koordinatı ve bağlantı doğruluğunun doğrulayıcısı olarak kabul edilmemeli.
Önceki Qwen başarısızlığı bütün VLM'lerin başarısız olduğunu kanıtlamaz; bu
makaledeki on örnek de bütün kullanıcı çizimlerinde güvenilirlik kanıtı değildir.

**SAM 2:** Prompt ile segmentasyon sunuyor; etiketleme ve tıklayarak maske düzeltme
aracı olarak denenebilir. Resmî tanımı room/door topology çıkarımı taahhüt etmiyor.
Tek başına plan graph'ının ana çözümü olarak seçmemek bizim görev değerlendirmemiz.
[Resmî depo](https://github.com/facebookresearch/sam2).

Kullanım koşulları model tercihini etkiliyor; burada otomatik izin talebi veya
kurulum başlatılmadı:

- CubiCasa5K [resmî lisansı](https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE)
  **CC BY-NC 4.0**. Açık indirme, sınırsız ticari kullanım izni anlamına gelmiyor.
- Raster2Seq kodu MIT; [yayımlanan checkpoint lisansı](https://github.com/Cornell-VAILab/Raster2Seq/blob/master/LICENSE-CHECKPOINTS)
  **CC BY-NC 4.0**, ticari SaaS inference'ı için bu izin yeterli olmadığını açıkça belirtiyor.
- DeepFloorplan deposu GPL-3.0 ve eski TensorFlow/Python ortamı kullanıyor. Mimari
  fikrinden yararlanmak ile kodu ürüne doğrudan katmak ayrı tercihler.
- SMP kütüphanesi [MIT](https://github.com/qubvel-org/segmentation_models.pytorch/blob/main/LICENSE).
  Seçilecek encoder checkpoint'i ve eğitim verisinin kullanım koşulları ayrıca
  kaydedilmeli; kütüphane lisansı tüm ağırlık ve veriye izin vermez.

## İlk somut deney

Yeni bir uzun eğitimden önce aynı validation çizimlerinde üç aday karşılaştır:
mevcut model, ResNet34 tabanlı yeni multi-task model ve uygun araştırma koşullarında
Raster2Seq hazır checkpoint'i. Genel region çıkarma başarısını önce ölç; yalnızca
marker eğitimine tekrar odaklanma. Yeni CNN'e başta region/boundary/instance
gözetimi ekle, sonra door endpoint ve owner atamasını birlikte değerlendir.

Tercihim, bu pilot için **ön eğitimli ResNet34 + çok görevli U-Net + kısıtlı
topoloji çözümü**. Başarı görülmeden yeni model varsayılana geçirilmez. Bu rapor
araştırma teslimidir; yeni ağırlık indirilmedi, servis çağrılmadı veya eğitim başlatılmadı.
