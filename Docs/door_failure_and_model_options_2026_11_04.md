# Kapı hataları ve model alternatifleri

Mevcut 20 yeni fotoğrafta 32 referans kapıdan 9'u son kapı önerisiyle eşleşiyor;
9 kapı önerisi var. Bu sayı yalnız bu yaklaşık etiketli, incelenmiş geliştirme
fotoğraflarına aittir. Sentetik F1 ile karıştırılmamalıdır.

Kapı işareti görme, açıklık görme, oda/koridor bölütleme ve ortak duvara atama ayrı
aşamalardır. Data_65'te 4 fiziksel kapı adayı var, 3'ü uyumlu ortak duvar olmaması
nedeniyle bağlanmıyor. Data_53'te koridor bölgesi eksik; iki kapı aralığı 512 piksel
kanıt karesinde yaklaşık 12,9 ve 9,1 piksel. Bu çözünürlük etkisinin olası olduğunu
gösterir, tek başına nedensel kanıt değildir. Data_63'te koridorlar oda olarak
öneriliyor ve 3 kapı kaçıyor. Data_58 ve Data_69'da da eksik/yanlış bölge geometrisi
var. L biçiminin kendisi tek sebep değildir; deneme_1'de iki kapı artık bulunuyor.

**Ek hata:** Data_68'de yalnız iki kapalı, bağlantısız oda varken klasik koridor
kurtarma katmanı 6 yanlış koridor ekliyor. Bu durum yeni oda sonuçlarını da bozuyor;
ensemble karşılaştırmasından önce düzeltilmesi veya açık bir gerileme kapısıyla
kontrol edilmesi gerekiyor. Bu incelemede çalışan algoritma değiştirilmedi.

| Fotoğraf | Doğru kapı / referans | Son kapı önerisi | Görüntü adayı | Bağlanamayan aday | Klasik katmanın eklediği koridor |
|---|---:|---:|---:|---:|---:|
| Data_51 | 1/2 | 1 | 0 | 0 | 0 |
| Data_52 | 0/1 | 0 | 1 | 1 | 0 |
| Data_53 | 0/2 | 0 | 0 | 0 | 0 |
| Data_54 | 2/2 | 2 | 2 | 0 | 0 |
| Data_55 | 0/0 | 0 | 0 | 0 | 0 |
| Data_56 | 0/2 | 0 | 0 | 0 | 0 |
| Data_57 | 0/1 | 0 | 0 | 0 | 0 |
| Data_58 | 0/2 | 0 | 1 | 1 | 0 |
| Data_59 | 2/2 | 2 | 2 | 0 | 2 |
| Data_60 | 0/0 | 0 | 0 | 0 | 0 |
| Data_61 | 0/1 | 0 | 0 | 0 | 0 |
| Data_62 | 0/0 | 0 | 0 | 0 | 0 |
| Data_63 | 0/3 | 0 | 1 | 1 | 0 |
| Data_64 | 2/4 | 2 | 3 | 2 | 1 |
| Data_65 | 1/4 | 1 | 4 | 3 | 0 |
| Data_66 | 0/2 | 0 | 0 | 0 | 0 |
| Data_67 | 1/1 | 1 | 0 | 0 | 1 |
| Data_68 | 0/0 | 0 | 0 | 0 | 6 |
| Data_69 | 0/2 | 0 | 0 | 0 | 0 |
| Data_70 | 0/1 | 0 | 0 | 0 | 0 |

Görüntü adayları bağımsız referansla eşleşmiş kapı sayısı değildir. Ham aday sayısı
ve son doğru kapı sayısı ayrı raporlanmıştır. Bölgelerdeki eşleştirme metriği tür
bağımsız kutu IoU kullanır; yalnız bölge F1'ine bakmak oda/koridor tür hatasını gizler.

## Araştırılan modeller

- CubiCasa5K: https://github.com/CubiCasa/CubiCasa5k . 5000 plan, çok görevli model ve
  yayınlanan eğitilmiş ağırlık bağlantısı var. İkinci bir oda/duvar modeli için aday;
  bizim serbest el fotoğrafları ve iki çizgili kapı işaretleri üzerinde sınanmadı.
- DeepFloorplan: https://github.com/zlzeng/DeepFloorplan . Oda sınırı ve oda türü için
  ortak öğrenme; duvar, kapı/pencere ve oda etiketleri var. Özgün uygulama eski
  Python/TensorFlow ortamı istiyor; doğrudan hazır değişim sayılmamalı.
- RoomFormer: https://github.com/ywyue/RoomFormer . Oda poligonları ve mimari elemanlar
  çıkarıyor; ancak girdi alanı 3B taramadan üretilen yoğunluk haritaları. Bizim PNG
  çizimlerine doğrudan uygun bir karşılaştırma modeli değildir.
- Sketch2BIM: https://arxiv.org/abs/2510.20838 . El çizimi ve insan geri bildirimiyle
  çok modlu model destekli bir iş akışı; 10 planlık çalışması hazır, bağımsız ve
  tamamen otomatik bir kapı dedektörü başarısı gibi yorumlanmamalı.

## Önerilen deneme sırası

1. Data_68 tipi yanlış koridorları ve oda/koridor tür hatalarını ayrı ölçmek.
2. Mevcut DINO ile mevcut U-Net'i aynı koordinatlarda tek tek karşılaştırmak,
   sonra doğrulamada ağırlıklandırılmış bir birleşimi sınamak. Aynı DINO'nun farklı
   eğitim turlarını ortalamak ilk tercih olmamalı; aynı hata kaynaklarını paylaşıyorlar.
3. CubiCasa5K modelini değiştirmeden kıyaslayıp tamamlayıcı hata yapıp yapmadığını
   görmek. Tamamlayıcıysa odayı/duvarı bu modelden, kapı adayını yerel dedektörden
   alan görev bazlı birleşimi denemek.
4. Kapı çevresinde yüksek çözünürlüklü yerel dedektörü ayrı ölçmek; aday konumları
   yalnız görüntü/model çıktısından seçilmeli. Önceki tek kırpım denemesi başarı
   getirmediği için yakınlaştırmanın tek başına çözüm olduğu varsayılmamalı.

Her yaklaşım için yalnız bölge F1 değil oda/koridor türü, kapı uçları, tamamlanmış
kapılar, doğru bölge çiftleri, yanlış bağlantı ve işlem süresi birlikte izlenmeli.
Bu araştırmada yeni model indirilmedi, ensemble çalıştırılmadı ve eğitim başlatılmadı.
