# Step 08 — Wall Graph ve Region Topology MVP

## Bu aşamanın amacı

Step 07, fotoğraftan pixel tabanlı `wall_candidate` çizgileri ve olası opening'ler çıkarıyordu. Step 08 bu kanıtları bir `Wall Graph` içine toplar, çizgi kesişimlerinde linework'ü böler ve kapalı yüzeyler bulmaya çalışır. Ardından opening'lerin hangi yüzeyleri bağlayabileceğine dair review edilebilir hypotheses üretir.

Bu çıktı henüz Unreal'a aktarılacak bir floor plan değildir. Koordinatlar `px` cinsindedir; çizimden centimeter ölçeği çıkarılmaz. Fiziksel duvarlar ile bir opening'i polygonization için kapatan sanal sınır birbirinden ayrı tutulur. Her topology sonucu `review_required: true` taşır.

## Uygulama

Ana algoritma `SketchPipeline/perception/topology.py` içindeki `build_topology` fonksiyonudur. `run.py`, Step 07'nin seçilen detector line'larını ve recovery line'larını bu fonksiyona verir.

1. Çizgiler, mevcut horizontal/vertical `axis` tahminlerine göre global küçük rotation çıkarılmış pixel frame'e taşınır ve aynı doğrultudaki yakın duplicate segmentler birleştirilir.
2. Yakın perpendicular junction'lar, duvarların horizontal/vertical yönünü koruyarak aynı anda hesaplanır. Önceki sürüm endpoint'leri sırayla en yakın noktaya taşıyor, bazı çizgileri eğiyor ve junction'da boşluk bırakıyordu. Yeni sürüm yalnızca wall'ın kendi doğrultusunda extension yapar. Temel tolerans `max(3 px, long_side × snap_tolerance_fraction)` şeklindedir; bu sınırın iki katına kadar extension ancak gözlenen çizginin devamında ink varsa denenir.
3. Collinear parçaların arasındaki boşluk, görüntüdeki stroke ile doğrulanmadan physical wall yapılmaz. `unmasked_wall_ink` mask üzerinde dar bir ribbon kullanılır; hem direction hem ink coverage kontrol edilir. Short `unknown` parçalar, text dışında kalıp mevcut güçlü bir wall'a ink ile bağlanabiliyorsa yerel olarak recover edilir. Bu recovery başka unknown parçaları zincirleme promote etmez. Accepted opening'in support pair'i duplicate merge'den korunur; reddedilmiş veya unresolved gap proposals bütün duvar birleşmelerini bloke etmez.
4. `opening_candidate` gap'leri solid wall yapılmaz. İki endpoint'in iki ayrı collinear support wall'a bağlanması gerekir. Supports aynı axis coordinate'e birlikte align edilir. Opening endpoint'leri genel junction extension sırasında kilitlenir; yakındaki tick/corridor junction'ına yalnızca gap'in en fazla %25'i kadar taşınabilir. İki uç birlikte hareket etse de gap'in en az yarısı korunur. Polygonization için kullanılan `virtual_boundary` ve physical wall ayrı source IDs ile saklanır. Attachment olmayan veya physical wall ile örtüşen boundary unresolved kalır.
5. Shapely `unary_union` kesişimlerde linework'ü nodelar. `polygonize_full` bounded faces ile birlikte `cut_edges`, `dangles` ve `invalid_rings` verir. Image border'a yapışık line artifacts floor boundary sayılmaz.
6. Dört köşeli, axis-aligned ve bounding box alanına göre yeterince dolu yüzey `rectangular_region_candidate` olur. Bu yalnızca shape hypothesis'tır; otomatik olarak `room` veya `corridor` denmez.
7. Bağlantı önerisi için valid virtual boundary'nin en az %95'i iki rectangular region'ın sınırında olmalı; iki yanında yakın örnek noktalar ilgili region'lara düşmelidir. Raw opening midpoint'inin iki oda yakınında olması yeterli değildir. Karşıt yönlerde opening'i olan ve unresolved boundary taşımayan region ayrıca `corridor_hypothesis` alabilir. Bu semantik etiketlerin tümü review gerektirir.

Wall Graph geometrik sınırları, Region Connectivity Graph geçiş hypotheses'larını temsil eder. İki region'ın komşu olması aralarında geçiş olduğu anlamına gelmez; geçiş için opening kanıtı gerekir. Step 08 region'ları hâlâ pixel uzayında olduğundan bu graph da ölçülü gameplay geometry sayılmaz.

## Çalıştırma ve inceleme

Düzeltilebilir local editor eklendi. `Saved/Step07/python/bin/python -m SketchPipeline.review.server` ile başlat; `http://127.0.0.1:8768/` adresinde wall/opening düzeltmesi, canlı graph, draft ve explicit reviewed revision işlemlerini kullan. Kullanım ve acceptance kuralları: `Docs/step08_topology_review.md`.

Ortam önceden kurulmuşsa repository kökünden:

```sh
Saved/Step07/python/bin/python -m SketchPipeline.perception.run --image Data/Data_3.jpeg --output Saved/Step08/my-review
Saved/Step07/python/bin/python -m SketchPipeline.perception.run --dataset --output Saved/Step08/my-dataset-review
```

`Saved/Step08/final-review-v4/index.html` güncel on-fotoğraflık review sayfasıdır. `final-review-v2` ilk topology baseline'ı olarak durur. Her fotoğraf için `topology_review.png` overlay, `topology.json` ise makinece okunur detaydır. Teal çizgiler physical wall evidence, orange çizgiler virtual opening boundaries, mor yüzeyler rectangular region candidates, amber yüzeyler unresolved opening boundary taşıyan candidates ve kırmızı yüzeyler unsupported faces'tır. Hiçbir renk kullanıcı acceptance'ı anlamına gelmez.

JSON'da `wall_graph`, `regions`, `region_connectivity_graph`, `corridor_hypotheses`, `polygonization` ve `issues` alanlarını incele. Onarımların nedenini `stroke_repairs`, `snap_adjustments`, `opening_endpoint_adjustments`, `opening_boundaries`, `recovered_short_line_ids` ve `local_opening_support_line_ids` açıklar. Dangles/cut edges'in koordinatları da `polygonization` altındadır. `region.topology_status` alanı `region_candidate`, `ambiguous_boundary` veya `unsupported_region` olabilir.

Shapely bağımlılığı `SketchPipeline/requirements-perception.txt` içinde pin edilmiştir. Step 08 kodunu çalıştırmadan önce mevcut Python environment'a requirements kurulu olmalı.

## Mevcut geliştirme sonucu

`Data_1`–`Data_10` üzerinde güncel pipeline uçtan uca çalıştı. Eski baseline yalnızca Data_3 ve Data_6'da bounded faces üretiyordu. Yeni sürüm dokuz fotoğrafta en az bir bounded face adayı üretiyor. Bu bir **accuracy oranı değildir**; fazladan ve yanlış yüzeyler hâlâ mümkündür.

| Çizim | İlk sürüm: faces / links | Güncel: faces / links | Yorum |
| --- | --- | --- | --- |
| Data_1 | 0 / 0 | 1 / 0 | Tek rectangular footprint recover edildi. |
| Data_2 | 0 / 0 | 0 / 0 | Açık kalan corner nedeniyle bounded face yok; review gerekiyor. |
| Data_3 | 1 / 0 | 2 / 1 | İç partition iki rectangular region'a ayrıldı. |
| Data_4 | 0 / 0 | 2 / 1 | Shared-wall opening iki region'a bağlandı. |
| Data_5 | 0 / 0 | 2 / 1 | Short fragments ve opening sınırı recover edildi. |
| Data_6 | 3 / 0 | 4 / 2 | Corridor hypothesis ve iki giriş var; fazladan dördüncü yüzey amber/ambiguous kaldı. |
| Data_7 | 0 / 0 | 2 / 0 | Yüzeyler non-rectangular/ambiguous; usable connectivity oluşmadı. |
| Data_8 | 0 / 0 | 2 / 1 | Kısmi reconstruction; room/corridor yapısı tamamlanmadı. |
| Data_9 | 0 / 0 | 1 / 0 | Footprint recover edildi; 600/450 dimension conflict bu aşamada çözülmedi. |
| Data_10 | 0 / 0 | 1 / 0 | Eksik topology ve unresolved openings devam ediyor. |

Step 07'nin OCR, line coverage ve opening evaluation aggregate'ları önceki run ile birebir aynı kaldı: opening candidates 11/11 matched, 16 predicted, precision 68.75%, recall 100%. Step 08'in altı connectivity edge'i ayrı, review gerektiren topology hypotheses'tır; bunlar için ölçülmüş precision iddiası yoktur.

Fotoğraf perception'ından bağımsız 14 deterministic fixture `SketchPipeline/tests/test_topology.py` içinde geçiyor. Rectangle/shared wall/T junction/corridor yanında order-independent junctions, ink olmadan boşluk kapatmama, ink ile detector fragmentation recovery, tiny opening'i physical wall'a çevirmeme, rejected boundary'den bağlantı üretmeme, opening'i tüketmeme ve corridor junction attachment davranışları kontrol ediliyor. Tüm Python suite: **94 test geçti**. Bu testler fixture contract'ını doğrular; OCR ve unseen-photo accuracy ölçmez.

```sh
Saved/Step07/python/bin/python -m unittest discover -s SketchPipeline/tests -q
```

Dataset çalışmasının log'u `Saved/Step08/final-run-v4.log`, toplu çıktısı `Saved/Step08/final-review-v4/report.json` içindedir.

Geliştirme datası daha önceki Step 07 threshold ayarlarında kullanılmıştır; sonuçlar bağımsız benchmark değildir. Prediction halen manual annotations okunmadan üretilir; references yalnızca dataset evaluator tarafından prediction sonrasında okunur. Ground truth output'a verilmez.

## Bilinen sınırlamalar ve sonraki iş

- Detector line'ları ve dimension/tick izleri bazı çizimlerde bölünmüş veya wall gibi sınıflandırılmıştır. Bu, polygonization'ı dangle bırakabilir ya da sahte region üretebilir.
- Tolerances hâlâ image resolution'a bağlı heuristics'tir; otomatik stroke-width calibration yapılmadı. Ink ribbon ve coverage eşikleri bu geliştirme fotoğraflarında denenmiştir; yeni çizimlerde doğrulanmalıdır.
- Açık exterior footprint için bounded region yoksa sistem room uydurmamalı. Bu case `no bounded region` olarak kalmalı veya kullanıcı review ister.
- Opening attachment ve region boundary coverage artık birlikte kontrol ediliyor; fakat one-sided/exterior opening ile eksik reconstruction veya false candidate her durumda otomatik ayırt edilemiyor. Ambiguous yüzeyler export edilmemeli.
- Corridor tanıma şimdilik zayıf bir semantic hypothesis'tır. İki opposed opening tek başına corridor kanıtlamaz; region şekli, komşuluk ve plan bütünlüğü de kontrol edilmelidir.
- Rectangle classification, aligned corners ve area ratio kullanan heuristic'tir; robust room reconstruction değildir.

### Bir sonraki iterasyonun sırası

1. Yeni synthetic fixture'lar topology contract'ı koruyacak şekilde tutulur.
2. Her gerçek çizimde detector output ve `topology_review.png` yan yana incelenir; eksik/bölünmüş/yanlış role atanmış line IDs belirlenir.
3. Line role ve endpoint attachment kuralları birer birer geliştirilir; aynı fixture suite ve dataset tekrar çalıştırılır.
4. Region recovery güvenilir olana kadar metric constraint solver'a başlanmaz.

### Step 08'in kalan kabul ölçütleri

1. Manual clean rectangle ve adjacent-room fixtures'larında tekil, stabil node/edge graph.
2. T junction'da bir uzun duvarın junction'da doğru split edilmesi.
3. Door/open passage virtual boundary'sinin physical wall olarak export edilmemesi.
4. Clean fixtures'ta room, direct shared-wall passage ve explicit corridor bağlantılarının beklenen topology'yi vermesi.
5. Broken, ambiguous veya unsupported çizimlerde yanlış region yerine açık review issue üretilmesi.

Bu kriterler sağlanmadan Step 09 metric constraint solving'e geçildiğinde topology hataları ölçülere taşınır. Önce Step 08 fixture'larını ve region-recovery davranışını sağlamlaştırmak gerekir.
