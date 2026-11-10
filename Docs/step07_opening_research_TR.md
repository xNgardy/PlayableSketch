# Step 07 opening detection — araştırma ve uygulama sonucu

Araştırma tarihi: 2026-10-15. Mevcut baseline: `Saved/Step07/final-review-v1/`.

**Başlangıç baseline'ı:** 11 opening'de 4 eşleşme. Contextual recovery ilk aşamada 9/11 opening buldu ancak 23 adayın yalnızca 9'u eşleşti. Sonra finite-segment endpoint attachment kontrolü ve küçük gap review eşiği eklendi. Son tam inference `Saved/Step07/opening-improvement/full-review-v4/` içine yazıldı: 11/11 eşleşme, 16 aday (**100% recall, 68.8% precision**), yani 5 unmatched aday. Önceki review ve annotations korunuyor. Bu on fotoğraf implementation geliştirmede kullanıldığı için sonuç **development-set ölçümü**, unseen-plan performans iddiası değildir.

## 1. Sorun nerede?

Wall length coverage yüksek olsa da opening endpoints doğru çıkarılmayabilir. Bir wall'ın çoğunu bulmak, kapının başladığı birkaç pixel'i bulmakla aynı ölçüm değildir. Mevcut LSD wall recall coverage %93.6 iken opening recall %36.4 olması bu nedenle çelişki değildir.

Kod incelemesinde `gap_evidence()` şu koşulları kullanıyor:

1. Supporting segment'lerin ikisi de önceden `wall_candidate` olmalı.
2. Aynı axis üzerinde, projection overlap olmadan ayrılmalı.
3. Lateral offset, image long side'ın %0.9'unu aşmamalı; mevcut 1600 px working images için 14.4 px.
4. Başka bir wall candidate gap midpoint'ini kapatmamalı.
5. Her iki uçta perpendicular context bulunmalı.

Bunlar aynı anda sağlanmazsa bir opening candidate oluşmuyor. Özellikle kısa ama gerçek wall fragment'ları `unknown` kalınca, sonraki ticks/junction evidence onları kurtaramıyor: segment daha gap aramasına girmeden eleniyor.

### Mevcut 7 miss için gözlemler

Aşağıdaki analiz manual gap endpoints ile yakın segment'leri **diagnostic amacıyla** locate eder. Bunlar production prediction'a verilmedi. Yakın bulunan bir segment çifti, her durumda doğru supporting pair olduğu anlamına gelmez; özellikle endpoint error büyükse başka evidence gerekir.

| Kaçan opening | Diagnostic bulgu | Öncelikli düzeltme |
| --- | --- | --- |
| Data_4 door | Yakın supporting pair'de biri `unknown`; offset 7.9 px, her iki uçta perpendicular evidence var | Candidate üretiminde role'ü hard gate yapma |
| Data_5 door | Masked input'ta yakın wall endpoints/ticks kayboluyor; yakın pair güvenilir değil | Unmasked local recovery ve tick protection |
| Data_6 sol entrance | Yakın pair'de biri `unknown`; offset 17.1 px, limit 14.4 px; iki uçta context var | Role filter + local alignment |
| Data_6 sağ entrance | Yakın pair'de biri `unknown`; offset 4.4 px; iki uçta context var | Role filter |
| Data_7 üst entrance | Yakın pair'de biri `unknown`; offset 24.7 px; iki uçta context var | Role filter + local alignment |
| Data_7 alt entrance | Masked input'ta bir tarafta endpoint evidence uzaklaşıyor | Local recovery; tek pair'e bağlı olmayan proposal |
| Data_8 sağ entrance | Kısa lower fragment'ın yakın endpoint'i masked input'ta kayboluyor | Short fragment recovery + corridor/junction proposal |

Data_4 ve Data_6 sağ entrance için erken role filter'ın engelleyici olduğu oldukça açık. Data_5/7-alt/8-sağ için yalnızca tolerance artırmak yeterli bir açıklama veya çözüm değil.

## 2. Text masking ablation: ölçülen fark

Aynı preprocessing, LSD ve cleanup ile text polygons verilerek/verilmeden karşılaştırma yapıldı. İkinci koşulda OCR mask uygulanmıyor. Aşağıdaki değerler manual opening uçlarına en yakın, aynı axis'teki detected endpoint'in working-image distance'ıdır.

| Case | Masked endpoints distance | Unmasked endpoints distance |
| --- | --- | --- |
| Data_5 door | 62.2 / 32.0 px | 6.8 / 2.0 px |
| Data_7 alt entrance | 90.4 / 4.3 px | 9.3 / 4.3 px |
| Data_8 sağ entrance | 4.2 / 78.1 px | 4.2 / 17.1 px |

Data_4 ve Data_6'daki fark küçük; onların ana problemi masking görünmüyor. Bu ayrım önemli: bütün fotoğraflara tek bir ayar uygulamak yerine, hangi stage'in evidence kaybettiğini biliyoruz.

**Bu ablation yeni opening precision/recall sonucu değildir.** Yakın endpoint'lerin geri gelmesi, doğru opening'in otomatik seçildiğini kanıtlamaz. Ayrıca unmasked detection daha fazla text stroke'u üretebilir. İki input'u birlikte kullanıp source/provenance saklamak gerekir.

## 3. Araştırmadan çıkan mimari yön

Raster-to-Vector çalışması wall junctions ile opening endpoints'ı ayrı primitives olarak ele alıp bunları geometric/topological constraints ile birleştiriyor. GLSP ise junction heatmaps ve line categories için graph-based bir yaklaşım kullanıyor. Bizim için çıkarım: opening kararı sadece iki uzun wall segment'inin arasındaki boşluğa bağlı kalmamalı; endpoints, ticks ve junction context birlikte kullanılmalı. Bu, paper'ların modelini doğrudan projeye koymamız gerektiği anlamına gelmez. [Raster-to-Vector paper](https://art-programmer.github.io/floorplan-transformation/paper.pdf), [GLSP paper](https://arxiv.org/abs/2303.03851).

Bizim input convention'ımız single-line, el çizimi, ölçeğe uymayan rooms ve ticks/gaps kullanıyor. Architectural door swing arc veya double-line wall sembolü varsayan hazır bir modelin bu çizimlere aktarımı ayrıca ölçülmeli. CubiCasa5K, ileride structural pretraining/karşılaştırma için kaynak olabilir; kendi çizim domain'imizin yerine geçtiği varsayılmamalı. Resmi repository ayrıca eski Python/PyTorch/CUDA ortamı tarif ediyor; bugünkü Mac pipeline'ına doğrudan takılabilen bir dependency değil. [CubiCasa5K repository](https://github.com/CubiCasa/CubiCasa5k).

## 4. Uygulanan değişiklik ve kalan işler

### Uygulanan: rejection logging ve contextual proposal

`SketchPipeline/perception/openings.py`, her makul gap proposal'ı için supporting segment ID/role/source, endpoint context, OCR ilişkileri, fit residual, gap ink fraction ve rejection reasons kaydeder. `unknown` kısa segment yalnızca yerel structural context ile desteklenirse proposal'a katılır; global olarak wall yapılmaz. Önceki hard role filter böylece gevşetildi.

### Uygulanan: masked + unmasked recovery

`geometry.py`, masked detector input yanında OCR mask uygulanmamış enhanced gray input'tan recovery segments çıkarır. Bu segmentler `unmasked` provenance ile saklanır. Opening code bunları yerel endpoint/context kanıtı olarak kullanır. Data_5 ve Data_7/8'de masking ablation'ın gösterdiği endpoint kaybına karşılık gelen somut düzeltme budur.

### Uygulanan: finite-segment endpoint attachment kontrolü

Her seçilmiş perpendicular context çizgisinde opening endpoint'in çizgi üzerindeki normalized projection parameter'ı kaydedilir. Endpoint, finite segment'ten yalnızca uzatımda kalıyorsa (`context_on_extension_only`) pair `unresolved_gap` olarak kalır. Bu, graph'ın ilk yerel bağlantı kontrolüdür; henüz tam room graph/face topology çözümü değildir.

Sonuçta recovery aşamasının 23 adayından 16'sı review candidate kaldı. Unmatched candidate sayısı 14'ten 5'e indi; bu gelişme 11/11 annotated opening match korunarak elde edildi. Konfigürasyonda `candidate_min_gap_fraction=0.023` bulunur. Working image uzun kenarının %2.3'ünden küçük opening, otomatik aday rolüne yükseltilmez; silinmeden `unresolved_gap` olarak saklanır. Bu eşik yalnızca mevcut development fotoğraflarında ölçülmüştür ve yeni, farklı kadrajlı çizimlerde doğrulanmalıdır.

### Kısmen uygulanan: robust support line

Gap support pair için OpenCV `fitLine`/Huber diagnostic fit ve residual eklenmiştir. Bu değer canonical wall endpoints'ı snap etmez. Henüz ink tabanlı yerel interval occupancy, fit residual/stroke width'ten türetilen adaptive uncertainty veya bağımsız proposal scoring yoktur.

### Henüz uygulanmadı: corridor/junction proposal

Şu an opening proposal'ları collinear gap pairs üzerinden üretilir. Ayrı corridor-boundary ve L/T-junction proposal generator yoktur. Step 08 graph bu eksik context'i ileride değerlendirebilir.

## 5. Yeni ölçüm ve yorum

| Ölçüm | Baseline | Recovery run |
| --- | ---: | ---: |
| Eşleşen opening | 4/11 | 9/11 |
| Predicted opening candidates | 4 | 23 |
| Precision | 100% (4/4) | 39.1% (9/23) |
| Recall | 36.4% | 81.8% |

İkinci run olan `full-review-v4`, finite-segment graph attachment ve küçük-gap review kontrolünü ekler:

| Ölçüm | `full-review-v1` | `full-review-v4` |
| --- | ---: | ---: |
| Eşleşen opening | 9/11 | 11/11 |
| Predicted review candidates | 23 | 16 |
| Precision | 39.1% | 68.8% |
| Recall | 81.8% | 100% |

Bu 10 fotoğraflık development setinde beş false candidate kaldı. Eşikler bu set incelenerek seçildiği için sonucu bağımsız genelleme kanıtı saymıyoruz. Geliştirme hedefi, yeni planlarda da baseline true positives'ı koruyup bu false candidates'ı azaltmaktır.

Recovery run Data_4, Data_6 (2), Data_7 (2), Data_8 (2) ve Data_10 (2) opening'lerini eşleştiriyor. Data_3 ve Data_5 opening'leri kaçıyor. Baseline'da bulunan Data_3 opening'i yeni candidate setinde korunmamış; Data_8'in iki opening'i korunup eşleşiyor. Data_3, Data_5, Data_6, Data_7 ve Data_8'de unmatched candidate'ler var. Bu sonuç, yeni branch'in yararlı evidence geri getirdiğini ve kabul kararının hâlâ fazla permissive olduğunu gösteriyor.

Tam review: `Saved/Step07/opening-improvement/full-review-v1/index.html`. Per-image metric ve matching: her Data_N içindeki `metrics.json`; proposal kanıtı ve rejection reasons: `working.json`. Annotation veya metric layout tahmin üretiminde kullanılmadı.

## 6. Sonraki implementation sırası

### A — Proposal ile review candidate kararını ayır

Önce her plausible segment pair için elenme nedenlerini sakla: `support_role`, `alignment`, `gap_length`, `blocked`, `endpoint_context`, `text_overlap`.

Ardından iki ayrı kavram kullan:

- **Opening proposal:** Daha geniş, henüz doğrulanmamış geometric hypothesis.
- **Opening candidate:** Evidence birleştirildikten sonra review'a sunulan daha güçlü hypothesis.

`unknown` segment, uygun local context varsa proposal'a destek verebilsin. Bu segment'i global olarak confirmed wall yapma. Text stroke'u, image border veya başka bir wall parçası da olabilir.

Kazanım: Gerçek bir opening, segment'in erken role etiketi yüzünden tamamen kaybolmaz. Risk: Daha fazla false proposal çıkar. Bunlar ayrı ölçülmeli; canonical observations'a bütün noise proposals doğrudan yazılmamalı.

### B — False proposal kaynaklarını ölç ve azalt

Aynı görüntü için iki line evidence branch tut:

1. Text azaltılmış branch: wall inference için daha temiz input.
2. Original/gray branch: kısa ticks, endpoints ve wall fragments için recovery input.

Önce detected endpoint neighborhoods ve paired perpendicular strokes çevresinde local recovery dene. OCR polygon boyutu ya da yakınlık nedeniyle bu bölgeleri tamamen silme. Unmasked branch'ten gelen evidence'ın source ID'sini ve neden kullanıldığını kaydet.

Data_5 gibi label'ın ticks'le birlikte OCR crop'a girdiği durumlarda, büyük text polygon'u bütün opening evidence'ını kaldırabiliyor. Mevcut long-stroke protection, kısa ticks'i korumaya yetmiyor.

Kazanım: Masking'in sildiği küçük ama kritik structural evidence geri değerlendirilebilir. Risk: `1`, `4`, `7` gibi digit strokes ticks'e benzeyebilir. İki taraflı context ve continuity kontrolü gerekir.

### C — Local support line ve interval modeli

Birbirine ait olabilecek fragments için ortak bir **support line hypothesis** kur. Bu, çizimde görünmeyen bir duvarı final geometry'ye eklemek değildir; candidates'ı kıyaslamak için kullanılan yardımcı referanstır.

Uygun local ink points/segment samples üzerinde robust fitting uygulanabilir. OpenCV `fitLine`, Huber/Welsch gibi distance functions ile fitting sağlar; mevcut dependency'de bulunur. [OpenCV fitLine](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html).

Mantık:

1. Local fragments'ın yaklaşık ortak direction'ını bul.
2. Points'ı bu direction üzerinde 1D coordinates'a project et.
3. Hangi intervals'da wall ink desteği var, hangilerinde yok kaydet.
4. Aradaki boş interval için endpoint/tick/junction evidence ara.
5. Fit residual ve local stroke width'e göre alignment belirsizliği belirle.

Böylece el çizimi nedeniyle 17–25 px kaymış gerçek parçaları, image genelinden hesaplanan tek bir 14.4 px limit ile otomatik elemek zorunda kalmayız. Bununla birlikte farklı paralel walls aynı support line'a zorlanmamalı. Global snap, bütün contour'u düzleştirme veya büyük gap kapatma bu aşamanın işi değil.

### D — Door ve open corridor için ayrı proposal yolları

Üç proposal yolu bir arada çalışsın:

- **Collinear gap proposal:** Ayrılmış wall fragments + boş interval.
- **Tick-pair proposal:** Yaklaşık aynı wall direction boyunca iki perpendicular marker + aralarındaki opening span.
- **Corridor entrance proposal:** İki corridor boundary'nin room tarafındaki uçları ve local L/T junction ilişkileri.

Corridor entrance için iki uzun collinear wall segment'i veya okunmuş door width text'i zorunlu olmasın. Özellikle corner'a yakın girişte kalan wall fragment çok kısa olabilir. Bu yol Data_8 sağ entrance gibi durumlar için anlamlı bir hipotezdir; başarısı implementasyon sonrasında ölçülecek.

Step 08'in Wall Graph mantığının bir bölümü bu context'i değerlendirmek için gerekli. Önce proposal recovery yapılabilir, sonra Step 08 graph bu proposals'ı destekleyebilir/reddedebilir. Bütün openings'i Step 08 başlamadan kusursuz çözmek zorunlu değil.

### E — Evidence fusion ve review

Her proposal için şu signals ayrı saklansın:

- Supporting wall continuity ve fit residual.
- İki endpoint'teki ticks/junctions.
- Gap içindeki wall ink desteği veya yokluğu.
- Nearby text polygon ve numeric alternatives.
- `D` marker varsa ek evidence.
- Text overlap, border ve incidental stroke break gibi karşı evidence.

Numeric width label destekleyici olsun; OCR hatası bütün opening'i ortadan kaldırmasın. `door_like`, `open_passage_like` ve `ambiguous` ayrımını koru. Score kullanılırsa bunun calibrated probability olmadığı açık olsun.

Ölçüler scale'e uygun çizilmediği için pixel gap'i `120 cm` ile oranlayıp label doğrulama yapma. Cm width/offset association Step 09'da çözülecek.

## 7. Öncelikli olmayan yaklaşımlar

**Büyük morphological closing:** Foreground'daki küçük boşlukları kapatmak için tasarlanmıştır. Bu projede gerçek door gap'lerini de kaldırabilir. Kullanılacaksa yalnızca temporary topology hypothesis üzerinde, original gap evidence korunarak denenmeli. [OpenCV morphology](https://docs.opencv.org/4.13.0/d9/d61/tutorial_py_morphological_ops.html).

**Sadece tolerance artırmak:** Data_6 sol veya Data_7 üst gibi alignment sorunlarında yardımcı olabilir; masking ile kaybolan endpoint'i geri getirmez, short fragment'ın role filter'da elenmesini de düzeltmez. Yan yana farklı walls'ın karışma ihtimali ayrıca test edilmeli.

**Yeni OCR modeliyle başlamak:** OCR accuracy ayrıca iyileştirilmeli. Ancak Data_4'te 180 cm okunmuşken opening kaçıyor; mevcut blocker geometry candidate mantığında. İlk opening düzeltmesi OCR modelini değiştirmeyi gerektirmiyor.

**On fotoğrafla büyük model training:** Bu on fotoğraf development set. Varyasyon üretmek yararlı ama yeni bağımsız plan/writer sayısını artırmaz. Learned junction/segmentation model'e ihtiyaç kalırsa önce aynı convention'da daha çeşitli annotations ve gerçekten ayrılmış evaluation data gerekir.

## 8. Deney ve kabul planı

Her değişiklik ayrı ölçülsün:

| Deney | Değişiklik |
| --- | --- |
| E0 | Mevcut baseline: 4/11 opening, 4 prediction |
| E1 | Contextual unknown support + rejection logging: recovery run'da uygulanmış |
| E2 | E1 + masked/unmasked local recovery: recovery run'da uygulanmış |
| E3 | E2 + robust fit diagnostics: kısmen uygulanmış; interval occupancy bekliyor |
| E4 | E3 + corridor/junction route: uygulanmadı |

Her deneyde proposal recall, final opening precision/recall, endpoint error, false candidates, wall coverage ve OCR numeric exact ayrı kaydedilsin. Mevcut matching tolerance değiştirilmeden baseline ile kıyaslansın; ayrıca daha sıkı endpoint tolerance'daki sonucu da raporlamak faydalı olur.

Hedef olarak 11 opening'in en az 9'unu bulmayı seçebiliriz; bu bir **engineering target**, araştırmanın kanıtladığı sonuç değil. Bugün bulunan dört opening kaybolmamalı; Data_1/2/9'daki incidental breaks gerçek door sayılmamalı. Data_10'daki missing cm values boş kalmalı.

Yeni negative/robustness cases: küçük kalem kopukluğu, label-wall overlap, tek tick, silik ikinci tick, corner'a yakın opening, kısa wall remainder, dar corridor, birbirine yakın parallel walls, blur, shadow ve perspective. Same-plan fotoğraf varyasyonları aynı split'te tutulmalı. Yeni plan/writer'larla küçük independent check set kurulmalı; yalnızca mevcut on fotoğrafta iyileşme generalization kanıtı değil.

## 9. Tekrar üretilebilir diagnostic artifacts

- `Saved/Step07/research/diagnosis.json`: GT-localized nearest-pair checks ve rejection conditions.
- `Saved/Step07/research/mask_ablation.json`: Masked/unmasked endpoint ve perpendicular context karşılaştırması.
- Aynı directory'deki `diagnose.py` ve `mask_ablation.py` sadece araştırma script'leri; production detector'a import edilmez.

Repository root'tan:

```sh
PYTHONPATH=. Saved/Step07/python/bin/python Saved/Step07/research/diagnose.py
PYTHONPATH=. Saved/Step07/python/bin/python Saved/Step07/research/mask_ablation.py
```

Manual ground truth bu iki script'te yalnızca hata bölgelerini incelemek için kullanılır. İyileştirilmiş prediction hiçbir şekilde bu endpoints veya expected widths ile doldurulmamalı.

## Arama motoruna yazılacak terimler

- `floor plan opening detection junction endpoints raster to vector`
- `hand drawn floor plan text graphics separation preserving lines`
- `robust line fitting Huber M estimator OpenCV fitLine`
- `collinear line segments interval gap detection`
- `floor plan corridor entrance junction graph`
- `line segment classification graph neural networks GLSP`
- `floor plan domain adaptation hand drawn architectural drawings`

İlk precision-focused attachment deneyi tamamlandı ve ölçüldü. Sıradaki iş, kalan Data_6/7/8 false candidates için room/corridor graph bağlamını kullanmak ve aynı zamanda farklı çizimlerdeki kısa gerçek opening'leri korumak. Ardından interval occupancy ve corridor/junction proposal yolu ölçülmeli. Yeni independent plans eklenene kadar sonuçlar development-set sonucu olarak raporlanmalı.
