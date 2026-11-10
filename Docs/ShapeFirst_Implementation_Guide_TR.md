# PlayableSketch — Shape-first implementation guide

Tarih: 21 Ekim 2026  
Durum: Plan ve aşama bazlı implementation kayıtları; güncel core teslim Step 5 kaydında belirtilir.  
Kapsam: Beş implementation aşaması. İlk hedef local web uygulaması; mevcut Unreal export/runtime yeniden kullanılır.

## Ürün kararı

Kullanıcı kabaca bir plan çizer. Sistem yazılı sayıları okumadan room, corridor, door ve bağlantı adaylarını çıkarır. Kullanıcı bunları görsel olarak düzeltir. Sistem başlangıç boyutları önerir; kullanıcı önerileri kullanabilir veya kendi boyutlarını girebilir. Onaylanan tasarım mevcut Unreal pipeline'ına gönderilir.

Bu, eski dimension-driven reconstruction yaklaşımına göre bilinçli bir ürün değişikliğidir: artık kağıttaki gerçek ölçüleri geri kurmuyoruz; çizimden esinlenen, kullanıcı tarafından boyutlandırılan bir level tasarlıyoruz.

- **Perception ve topology:** image coordinates / normalized coordinates; fiziksel birim yok.
- **Sizing:** application presets + yaklaşık görünür oranlar + bağlantıların geometrik gerekleri üzerinden tasarım önerisi.
- **Export:** kullanıcı tarafından kabul edilmiş fiziksel boyutlar; mevcut Unreal contract nedeniyle içeride `cm`.
- Yazılı sayılar okunmaz, association yapılmaz, görünür sayı bulunmaması hata değildir. Eski resimde sayı varsa bu sayı bir boyut kaynağı haline gelmez.
- Kullanıcıya “çizimden ölçüldü” denmez. Ürün açıklaması: **“Suggested sizes are starting points. Adjust them to suit your level.”**
- OCR'ın kaldırılması tek başına dalgalı çizgi sorununu çözmez. Shape perception ve geometric regularization ayrıca geliştirilecektir.

Önceki [drawing convention](drawing_convention_v1.md) ve Step 05–14 belgeleri eski akışın geçmiş sözleşmesidir. Yeni varsayılan upload akışı, bu guide implement edilip doğrulandıktan sonra shape-first olacaktır. Eski accepted dosyalar/annotations dönüştürülmez veya overwrite edilmez. Eski OCR yolu internal regression/CLI için korunabilir; normal kullanıcıya iki teknik pipeline seçtirilmez.

## Hedef kullanıcı akışı

```text
Upload sketch
  → AI shape/connection proposals
  → editable plan over the original image
  → suggested sizes + live generated-plan preview
  → user corrections / size overrides
  → review and confirm
  → validated Unreal export / existing runtime import
```

Web arayüzü aynı workspace içinde bu akışı sunar. Kullanıcı wall graph koordinatları veya solver equations girmek zorunda kalmaz. AI başarısız olsa da image açılır ve room/corridor/door araçları kullanılabilir.

### Desteklenen çizim dili

- İlk sürümde single-floor, top-down, orthogonal tasarım; her room ve her corridor segment rectangular veya square kalır.
- Dalgalı çizilmiş bir rectangle, temiz rectangle önerisine dönüşebilir; orijinal ink değiştirilmez.
- Dış sınır tek rectangle olmak zorunda değildir. Staggered rooms, direct shared walls, birden fazla rectangular corridor, T junctions, branching ve cycles destek kapsamındadır.
- Bir shared wall tek fiziksel wall'dır. Door: wall gap + iki perpendicular endpoint tick. Tick tek başına door sayılmaz; kırık stroke tek başına da door sayılmaz.
- Corridor dönüşü iki rectangular segment + açık interface olarak modellenir. Tek L-shaped room veya corridor polygon'una sessizce çevrilmez.
- Yakınlık, çizgi kesişmesi veya bounding-box overlap otomatik olarak passage oluşturmaz. Door/open interface/corridor kanıtı veya kullanıcı kararı gerekir.
- Room/corridor türü belirsizse kullanıcı değiştirebilir. Düzgün olmayan her şekli zorla rectangle'a tamamlamak yerine belirsizlik gösterilir.
- Wall thickness/height settings; Start/Goal kullanıcı seçimidir.

## Step 1 — Shape-first contract ve boyutlandırma politikası

**Implementation kaydı (22 Ekim 2026):** Contract, versioned policy, adapter mapping,
compatibility notu ve küçük fixtures eklendi. Kapsam, doğrulama sınırları ve test
komutları: [Step 1 teslim notu](step01_shape_authoring.md). Joint solver ve çalışan
canonical adapter Step 3; web/model/runtime entegrasyonu sonraki aşamalardır.

**Amaç:** Sayı okumaya bağlı olmayan veri modelini ve kullanıcı kararlarının anlamını sabitlemek.

**Bağımlılık:** Yok; mevcut repository contract/parser/validator incelemesiyle başlanır.

**Input:** Source image, mevcut canonical schema, topology review, metric solver ve runtime contract.

**Yapılacaklar:**

1. Yeni, versioned bir authoring document tanımla: `playablesketch-shape-authoring/2.0`. Image evidence, interpreted topology ve physical design state ayrı katmanlar olsun. Yeni state eski OCR observations formatına sahte text ekleyerek uydurulmasın.
2. Stable entity IDs ile `room`, `corridor_segment`, `wall`, `junction`, `opening` ve `connection` kayıtlarını tanımla. Opening'in supporting wall/interface'i, bağlı iki entity'si ve `door / open_passage` türü açık olsun. İki room arasındaki birden fazla door ayrı kayıtlar olarak kalır.
3. Pixel geometry, normalized geometry ve original↔working transforms saklansın. Physical origin/translation anchor ve global orientation ayrı tutulur; image crop/resolution değişince önerilen boyut değişmemelidir.
4. İki ayrı provenance izle: geometry kaynağı (`model / regularized / user`) ve size kaynağı (`preset / proportion_suggestion / user_override`). Kullanıcının öneriyi kabul etmesi onu “görüntüden ölçülmüş gerçek” yapmaz.
5. Her ayarlanabilir değer için value, origin, lock durumu, önceki suggestion ve bağlı authoring revision saklansın. Unknown/ambiguous interpretation için açık state olsun; doğrulanmamış bir sayı “confidence %95” gibi sunulmasın.
6. Connection representation'da shared span, door interval, corridor interface ve normalized near-edge placement tanımlansın. UI'da door position corner/local T junction → near opening edge üzerinden ayarlanır; engine center offset dönüşümü adapter sorumluluğudur.
7. Yeni öneri politikasını eski exact measurement solve yolundan ayır. Preset/proportion soft preference; kullanıcı lock'ları ve geçerli structural relationships hard constraint olsun. Topology edit sonrası etkilenen suggestion/binding'ler stale işaretlensin, aynı ID üzerinden yanlış yere taşınmasın.
8. Yeni authoring state'ten mevcut `playablesketch-layout/1.0` contract'a adapter tasarla. Ek v2 metadata authoring document'te kalır; strict Unreal parser'a tanımadığı field gönderilmez. Mevcut `configured`, `derived`, review ve notes alanları doğrulukla kullanılır; acceptance olmadan inferred değerler validated ilan edilmez.

**Başlangıç preset'leri — ürün tasarım tercihi, ölçüm veya mimari standart değil:**

| Entity/setting | Fallback başlangıç değeri | Kullanıcı kontrolü |
| --- | --- | --- |
| Room | width 500 × depth 400 cm | Width/depth, aspect lock opsiyonu |
| Corridor segment | length 400, centerline width 200 cm | Length/width ve interface placement |
| Door | clear width 120, height 220 cm | Clear width ve near-edge offset |
| Walls | thickness 20, height 300 cm | Global settings |

Bu değerler her room'a aynen kopyalanmaz; Step 3 oranları ve topology'yi birlikte değerlendirir. Geçerli bir ortak çözüm bulunamazsa fallback değerleriyle sahte bir valid layout üretilmez. Kullanıcı boyutları serbestçe değiştirebilir; geometrik olarak imkansız bir birleşim export edilemez.

**Teslim:** Schema + versioned policy/config + adapter mapping + migration/compatibility notu + küçük contract fixtures.

**Kontroller / bitiş koşulu:** Text/OCR olmadan document oluşturuluyor; aynı bağlantıda çoklu doors ve corridor bends temsil ediliyor; size origin ile acceptance ayrı; eski accepted files ve source images değişmiyor. Numbered ve unnumbered input yeni akış için aynı kurala tabi.

## Step 2 — Dalgalı çizimlerden AI geometry ve connection proposals

**Implementation kaydı (22 Ekim 2026):** Yerel segmentation model adapter'ı,
regularizer, shape-only proposals CLI/job API, manuel düzeltme aracı ve ölçülen
karşılaştırma galerisi teslim edildi. Sentetik development hedefleri karşılandı;
insan çizimlerinde otomasyon kalitesi doğrulanmadı ve seçilen modelin sonuçları
zayıf kaldı. Kapsam, başarısızlıklar ve test kanıtı: [Step 2 teslim notu](step02_shape_proposals.md).

**Teşhis güncellemesi (3 Kasım 2026):** Aynı modelle giriş hazırlama ve
model/decoder ayrımı ölçüldü. Deneysel kırpma + 512 kare girdide 15 referans
bölgenin 12'si bulundu; kapı/geçiş ve decoder ölçek sorunları sürüyor.
Varsayılan akış değiştirilmedi. [İnsan çizimleri teşhis raporu](step02_human_input_diagnosis_2026_11_03.md).

**Decoder düzeltmesi (3 Kasım 2026):** Sabit geometri frame'i + native opening
kanıtı ve paired tick kontrolleriyle deneysel `refined` / `refined-full` profilleri
eklendi. Aynı 512 tam görüntü girdisinde doğru opening 1/17'den 6/17'ye çıktı
(4 Kasım düzeltmesi: incidental kırık opening paydasından çıkarıldı);
sentetik exact topology 43/60 korundu. İnsan opening recall hedefi hâlâ karşılanmadı.
[Uygulama, başarısız adaylar ve doğrulama](step02_decoder_refinement_2026_11_03.md).

**İnsan verisiyle eğitim (4 Kasım 2026):** Eksik opening galerisi, maskeli yapısal
etiketler, hedefli eğitim ve ayrı plan testi tamamlandı. Önceden incelenen 6 planda
10/17 opening konumu bulundu; doğru attachment 7/10. Ayrı 9 planda yalnızca 2/18
opening bulundu ve sentetik kontrol geriledi. Yeni model kabul edilmedi;
varsayılan korunuyor. Otomatik insan algılama hâlâ açık iş.
[Eğitim, başarısız adaylar ve sonuçlar](step02_human_adaptation_2026_11_04.md).

**DINOv2 deneyi (4 Kasım 2026):** Standart Apache-2.0 DINOv2 ViT-S/14 sabit encoder
ve proje içinde eğitilen segmentation/keypoint decoder çalıştırıldı. Eski test
grubunda region 7/26→19/26, opening 1/20→4/20; kapı endpoint 20/24 bulundu.
Bu geçmişte incelenmiş development verisidir. Sentetik bağlantı başarısı gerilediği
için aday yalnızca ayrı deney arayüzünde, varsayılan değişmedi.
[Yöntem, sonuçlar ve çalıştırma](step02_dinov2_pilot_2026_11_04.md).

**Decoder 2.4 (4 Kasım 2026):** Aynı DINO maskelerinde destekli küçük bölge kurtarma,
ortak sınırları birlikte uzlaştırma ve yuvarlak endpoint haritalarına uygun mantıksal
sınır kapanışı eklendi. Eski testte region 19/26→24/26, opening konumu 4/20→8/20;
doğru owner'lı bağlantı 4/19→7/19. Sentetik doğru bağlı opening 91/160→133/160.
Ek fazla bölgeler ve bir yanlış sentetik bağlantı nedeniyle review gerekliliği
korunuyor; model yeniden eğitilmedi ve global varsayılan değişmedi.
[Değişiklik, regresyonlar ve testler](step02_decoder_recovery_2026_11_04.md).

**Yerel duvar takibi entegrasyonu (4 Kasım 2026):** Sabit maskelerle dört kollu
deneyde B kolu eski testte doğru bağlantıyı 7/19→12/19 yükseltti. Yalnızca B,
standart DINO'nun refined profillerinde decoder 2.5 olarak etkinleştirildi;
global U-Net varsayılanı korunuyor. 110 cached örnekte deney geometrisi, üç gerçek
worker'da model maskeleri ve kapılar doğrulandı. Yeni yazar doğrulaması hâlâ açık.
[Kapsam ve doğrulama](step02_local_wall_tracking_integration_2026_11_04.md).

**Koridor/açık geçiş entegrasyonu (4 Kasım 2026):** Decoder 2.6, güçlü kanıtla
koridor fit'i ve oda taşmasını düzeltip açık-interface adaylarını ayrıca doğruluyor.
Eski test region 24/26→26/26, doğru bağlantı 12/19→16/19. Yeni yanlış bağlantı
oluşmadı; train'de bir ek eşleşmeyen region var. Üç eski-test passage ve validation
hataları sürüyor. DINO refined yolunda etkin; global varsayılan değişmedi.
[Sonuçlar ve kalan sorunlar](step02_corridor_passage_2026_11_04.md).

**Amaç:** Tek tek düz stroke bulmaya dayanan kırılgan akış yerine region/stroke/junction kanıtlarını birleştirerek intended rectangular plan önermek.

**Bağımlılık:** Step 1 contract.

**Input:** JPEG/PNG image; physical dimensions ve OCR transcription kullanılmaz.

**Yapılacaklar:**

1. Shape-only inference entry point ekle. Yeni job'da numeric OCR, numeric parsing ve dimension association çağrılmasın. Eski yazılar/grid/title gibi distractor ink yapısal kanıtla ayrıştırılsın; yazı olup olmadığını sınıflandırmak sayı okumak değildir.
2. Original image'i koruyarak normalize/deskew ve stroke-scale-aware cleanup yap. Grid suppression yalnızca kanıt yeterliyse çalışsın; dark wall/tick kesişmelerini veya gerçek corridor boşluklarını silmesin. Ham ve temizlenmiş kanıt birlikte kullanılabilsin.
3. Gerçek bir **learned vision adapter** çalıştır: structural strokes/regions, junction/door marker keypoints veya bunların proposal'larını üretsin. İlk aday aile segmentation/keypoint + deterministic graph decoder; VLM proposal adapter aynı contract üzerinden karşılaştırılabilir. CV-only fallback ayrı adlandırılır; klasik heuristic'i “AI model” diye sunma.
4. Model/provider seçimini aynı frozen development set'teki küçük pilot ile yap, sonra config/model hash'ini sabitle. Önceki local Qwen pilotunu varsayılan çözüm olarak devralma: [mevcut pilot](geometry_multimodal_pilot_results_2026_10_19.md) wall/connection başarısını kanıtlamadı ve hybrid'e ek geometry katkısı vermedi. Bu bulgu tüm VLM'lerin başarısız olacağını da göstermez.
5. Dense supervision gerekiyorsa yeni clean/wavy synthetic renders ile wall/region/tick/junction masks üret; mevcut gerçek verideki approximate polygon traces'i pixel-perfect background mask sayma. İnsan çizimleri üzerinde gerekli geometry etiketlerini ayrıca kontrol et. Eğitim kapsamı, kaynak ve model lisansı implementation sırasında kayda alınır; bu guide tek başına bir eğitim çalıştırmaz.
6. Wavy stroke'ları parçalardan ortak intended axis'e robust fit et. Corner/junction'ları stroke genişliğine ve image boyutuna göre bounded snap et; büyük boşluğu sadece closure sağlamak için birleştirme. Logical closed boundary ile physical door gap'i ayrı tut.
7. Room rectangles, corridor segments, shared walls, T/cross junctions ve opening intervals için birden çok alternatif üretilebilsin. Door için gap + karşılıklı tick desteği ve iki geçerli taraf aranır. Serbest ölçü çizikleri/digits door'a çevrilmesin.
8. Geometric regularizer/graph decoder rectangle validity, unique shared-wall ownership, attachment ve non-overlap kontrollerini yapsın. Bağlantı model önerisi olarak kalsın; düşük kanıt varsa `Needs attention`, otomatik kesin kabul yok.
9. Timeout, model unavailable veya boş detection durumunda image + manual tools açılabilsin. Backend/model ve gerçek elapsed time kaydedilsin. Cloud provider seçilirse image transmission ayrıca açıkça kararlaştırılır; local UI otomatik olarak cloud upload yetkisi sayılmaz.

**Değerlendirme:** Region precision/recall ve geometry error, door precision/recall, attachment doğruluğu, exact topology, duplicate/false connections, latency ve gerçek correction time. Rectangle bounding-box başarısı tek başına yeterli değil.

Mevcut 50 insan çizimi ve bunların synthetic/augmented türevleri **development** verisidir. Parent plan/writer/capture grupları split'ler arasında karışmaz. Yeni dalgalı, sayısız ve farklı writer çizimleri bağımsız evaluation için toplanır; yoksa unseen-writer sonucu bilinmiyor diye raporlanır. Synthetic-only test ile insan genellemesi iddia edilmez.

**Teslim:** Çalışan model adapter + regularizer + proposals API/job output + annotated comparison gallery + measured baseline karşılaştırması.

**Kontroller / bitiş koşulu:** Gerçek model inference çalışıyor ve sürümü izleniyor; wavy/grid/stray-mark, shared wall, iki door, branching/T ve cycle fixture'larında outcomes raporlanmış; numeric OCR çağrısı yok; belirsiz veya başarısız sonuçlar düzenlenebilir. Pilot başarı hedefleri karşılaştırmadan önce dondurulur; karşılanmayan otomasyon hedefleri saklanmaz ve manual fallback AI başarısı diye sayılmaz.

## Step 3 — Tutarlı size suggestions ve kullanıcı override'ları

**Implementation kaydı (4 Kasım 2026):** Ortak kısıtlı boyutlandırma çekirdeği,
otomatik öneriler, edit/lock/reset ve oran kilitleri, son geçerli önizlemenin
korunması, revision kontrollü job API ve strict canonical draft adapter uygulandı.
110 kayıtlı AI topolojisinin tamamı metric-valid önizleme üretti; bu algılama
doğruluğu değildir. 114 benzersiz test geçti. Kullanıcı workspace'i Step 4,
onaylı snapshot export/Unreal zinciri Step 5 olarak açık kalır.
[Teslim, API ve doğrulama](step03_shape_sizing_2026_11_04.md).

**Amaç:** Her room/corridor/door için makul, açıklanabilir ve düzenlenebilir başlangıç boyutlarını ortak bir geometrik çözümde üretmek.

**Bağımlılık:** Step 1; Step 2 çıktısı veya kullanıcı tarafından çizilmiş aynı contract'taki topology.

**Input:** Interpreted topology, approximate normalized placement/aspect ratios, design presets ve user locks. Yazılı ölçü yok.

**Yapılacaklar:**

1. Size proposal engine kur: preset scale, region aspect/relative area, approximate spacing ve selected design scale birlikte soft preference olsun. Bir image'den tek başına gerçek dünya scale'i bulunabildiği iddia edilmesin.
2. Örnek: yaklaşık 200×160 px room A, 120×160 px room B için A=500×400, B≈300×400 başlangıcı önerilebilir. Bu yalnızca design scale tercihidir. Image iki kat resample edilince aynı öneri gelmelidir; çizim ölçeğe uygun değilse kullanıcı oranları değiştirebilir veya preset'e dönebilir.
3. Tüm entities'yi **joint layout solve** ile ele al. Region başına bağımsız width/depth atayıp shared walls ve cycles'ı bozma. Global translation'ı tek anchor ile gider; shared coordinates, ordered junctions ve interface alignment'ı koru. Dış sınırı rectangle'a zorlama.
4. Positive room sizes, rectangularity, non-overlap, doğru shared span/door attachment, door containment ve corridor interface sürekliliği hard geometry koşullarıdır. Mantıklı boyut/aralık tercihleri soft'tur; kullanılan her tasarım varsayımı kaydedilir.
5. Door width physical clear opening; corridor width wall centerline basis olsun. Near-edge offset'in referans köşesi/T junction'ı ve yönü UI'da highlight edilsin. Engine center offset = reference direction'a göre near edge + yarım opening width dönüşümünden türetilsin. Aynı shared wall üzerindeki door intervals çakışmasın.
6. Room, corridor length/width, door clear width/offset için doğrudan edit + lock + reset-to-suggestion ekle. Önce placement oransal tercih olabilir; kullanıcı offset'i kilitlerse hard input olur. Artık bilinçli bir suggestion olan bu placement, eski “ölçülmüş offset” gibi sunulmaz.
7. Edit sırasında bağlı geometry için local/global recompute yap. Kullanıcının değiştirdiği/locked değeri koru; unlocked defaults hareket ederse etkilenen entities ve before/after preview göster. Önceden elle girilmiş değer sessizce yeniden önerilmez.
8. İmkansız lock kombinasyonunda son geçerli preview korunur; draft input da kaybolmaz. İlgili room/wall/door highlight edilir; hangi lock'ların çakıştığı ve olası çözümler gösterilir. Kullanıcı adına door silme, corridor daraltma veya ölçü değiştirme yok.
9. Units conversion/bounds ve finite-number validation uygula. Presetler ve recommendation policy versioned/deterministic olsun. “Accept suggested sizes” toplu onayı mümkün; kullanıcı her default'u tek tek yazmak zorunda değildir.

**Teslim:** Proposal/preview/recompute API, constraint diagnostics ve authoring→canonical adapter'ın test edilen çekirdeği.

**Kontroller / bitiş koşulu:** Her entity'nin düzenlenebilir boyutu ve kaynağı var; uniform resize/crop öneriyi scale etkilemiyor; kullanıcı lock'ları korunuyor; aynı wall'da çoklu doors, staggered layouts, corridor turns/T junctions ve cycles tutarlı. Aşırı dar opening veya imkansız room edit'i anlaşılır biçimde bloklanıyor. Şekil/oran suggestion'ı hiçbir yerde source measurement diye export edilmiyor.

## Step 4 — Profesyonel, kullanıcı dostu web workspace

**Implementation kaydı (4 Kasım 2026):** Tek workspace, Sketch/Plan/Compare,
görsel araçlar, gerçek sizing inspector'ı, metadata ve snapshot confirmation
uygulandı. 122 Python testi, 13 bellek içi JavaScript durum kontrolü ve ayrı
gerçek DINO→sizing backend akışı geçti. **Tarayıcı onay hizmetinin kullanım
sınırı nedeniyle gerçek browser etkileşimi, ekran görüntüleri ve görsel/a11y
kabul kontrolü tamamlanamadı. Step 4'ün bitiş koşulu henüz doğrulanmış değildir.**
Bu satırlar ilk Step 4 doğrulamasının tarihsel durumudur. Step 5 sırasında tarayıcı sınırı kalktı; gerçek sample→settings→confirm→ZIP indirme ve ayrıca image upload→DINO workspace akışı doğrulandı. Export artık açıktır. Tam erişilebilirlik ve tüm cihaz boyutları için ürün sertifikasyonu iddiası yoktur.
[Uygulama ve doğrulama sınırları](step04_workspace_2026_11_04.md).

**Amaç:** İki teknik review ekranını kullanıcı açısından tek, anlaşılır authoring deneyimine dönüştürmek.

**Bağımlılık:** Step 1–3; UI skeleton mock state ile erken yapılabilir, acceptance gerçek API'lerle doğrulanır.

**Ürün yüzeyi:** English UI, PlayableSketch branding. Kullanıcıya `Step 08`, `Step 10`, pipeline stage numaraları, pixel graph jargon'u, debug IDs, schema names veya solver rank gösterilmez. Guide'daki Step numaraları yalnızca geliştirme planına aittir. Normal draft kaydı olabilir; ürünün bütününe draft/demo etiketi konmaz.

**Yapılacaklar:**

1. Upload landing: drag/drop + **Upload sketch**, desteklenen çizim örneği, **Use a sample**, kısa number-free drawing açıklaması. Boyut/hata bilgisi açık; inference sırasında **Analyzing your sketch…**, cancel/retry ve recoverable failure.
2. Tek workspace: source overlay ve generated clean-plan preview; center canvas, entity list, context inspector ve sabit action bar. **Sketch / Plan / Compare**, zoom/pan/fit ve selected entity'nin iki görünümde highlight'ı.
3. Kullanıcı araçları: **Add room**, **Add corridor**, **Add door**, **Connect**, **Move**, **Resize**, **Delete**, **Undo/Redo**. Rectangle çizmek dört wall'ı ve shared boundary handling'i birlikte üretir. Yalnızca endpoint koordinatı yazma zorunluluğu yok.
4. Entity inspector: name/type, width/depth veya corridor length/width; door width, attached entities ve position. Size badge: **Suggested / Custom**. **Keep proportions**, **Lock size**, **Reset size**. Yanlış room/corridor classification kolayca değiştirilebilir.
5. Kullanıcı doğrudan shared wall üzerine door koyabilir; corridor endpoint'ini room/interface'e attach edebilir; yanlış connection'ı silebilir. Silme/resize sonrası etkilenen ilişkiler gösterilir; stale doors başka wall'a sessizce attach edilmez.
6. **Needs attention** listesi tıklandığında ilgili öğeye gider. Mesaj örneği: “This door no longer fits on the shared wall.” veya “Choose which room this corridor connects to.” Ham solver error normal UI'ya taşınmaz.
7. Size editing canlı preview, dirty/pending göstergesi ve unsaved-change koruması; stale response yeni seçimi overwrite etmez. Source sketch şekli ile düzenlenmiş metric plan farklılaştığında ikisi de ayrı ve anlaşılır kalır.
8. Settings: wall/floor settings; gerekirse advanced panel. Play için Start/Goal seçimi; export-only ile gameplay validation arasındaki fark kullanıcı dilinde açıklanır.
9. **Review plan → Confirm plan → Export for Unreal** eylemleri. Review summary'de room/corridor/door counts, unresolved items ve önerilerin başlangıç değeri olduğu kısa açıklama. Normal akışta revision string kopyalama veya iki ayrı approval ekranı zorunluluğu olmasın.
10. Keyboard access, visible focus, selected-state contrast, renk dışında ikon/metin, sayı alanı units/min/max, responsive inspector ve net loading/error/empty/success states doğrulansın. Teknik provenance/debug bilgisi yalnızca advanced details içinde.

**Teslim:** Gerçek backend'e bağlı web workspace; temiz ürün copy'si; before/after screenshots ve browser interaction kaydı.

**Kontroller / bitiş koşulu:** Kullanıcı failed detection'dan başlayıp rectangle/corridor/door ekleyerek geçerli plan oluşturabiliyor; AI önerisini düzeltebiliyor; boyutları değiştirebiliyor ve tekrar açınca state korunuyor. Normal ekranlarda Step numaraları/OCR measurement workflow yok. Sadece mockup veya screenshot, çalışan UI teslimi sayılmaz.

## Step 5 — Unreal delivery, persistence ve uçtan uca acceptance

**Implementation kaydı (4 Kasım 2026): Core local teslim tamamlandı.**
Exact-snapshot confirmation, immutable validated ZIP, versioned shape-first jobs,
source/model/policy hash bağları, mevcut runtime transport uyumluluğu ve teknik ID
kopyalamadan seçen local launcher uygulandı. 135 Python testi ve 15 bellek içi JS
kontrolü geçti. Gerçek tarayıcıdan sample export/download doğrulandı. Paketli Mac
uygulamasında gerçek DINO image job'u → açık test düzeltmeleri → aynı canonical
layout import → gerçek Pawn Goal; ayrı süreçte restart ve servis kapalı offline
retention geçti. Otomatik algılama doğruluğu ve manual düzeltme başarısı ayrı tutulur;
yeni unseen-writer accuracy sonucu yoktur. Engine checks yalnızca Unreal çalıştıktan
sonra geçerli; bundle bunları `not_run` olarak işaretler.
[Ayrıntılı kanıt, kullanım ve sınırlar](step05_shape_delivery_2026_11_04.md).

**Amaç:** Yeni shape-first tasarımı mevcut güvenilir geometry/runtime hattına bağlayarak local ürün akışını tamamlamak.

**Bağımlılık:** Step 1–4.

**Yapılacaklar:**

1. Yeni authoring revisions, inference jobs, suggestions ve user changes için immutable history/persistence ekle. Raw image, raw AI output ve user-approved tasarım ayrı saklansın; accepted dosya tekrar öneri çalıştırınca değişmesin.
2. Job API'ye versioned shape-first mode'u ekle ve doğrulama sonrasında yeni web upload'larında default yap. OCR model/environment failure shape-only job'u engellemesin. Cancel/retry/cache key; model/policy/contract sürümü ve source hash'i kapsasın.
3. Güncel topology + sizing revision + settings üzerinden canonical cm layout üret. Schema, geometry ve requested gameplay checks yeniden çalışsın. Kullanıcı onayı yalnızca gösterilen kaydedilmiş snapshot için geçerli; edit/inference recompute sonrası yeniden confirmation gerekir. User acceptance geometry geçerliliğinin yerine geçmez.
4. Mevcut `validated_layout` download ve selected-revision job endpoints'iyle Unreal import'u koru. Sayı/evidence eşleme zorunluluğunu yeni authoring adapter'da kaldır; fake OCR/GT linkleri üretme. Provenance için mevcut schema yeterli değilse explicit versioned schema/parser migration ve geriye uyumluluk testleri eklenir; strict validator bypass edilmez.
5. Web tarafında **Export for Unreal** indirilebilir validated dosya/bundle sunsun. Bundle gerekirse strict canonical JSON + ayrı authoring/provenance manifest içersin. Browser doğrudan local Unreal'ın dosyalarını yazabildiğini varsaymasın.
6. İlk zorunlu teslim download→mevcut importer/runtime akışı. Mevcut local runtime selected-job import da yeni jobs ile çalışmalı. Otomatik browser→app handoff ayrı isteğe bağlı iyileştirme olabilir; kullanıcıya teknik job/revision kopyalatmayı ana web export deneyimi haline getirme.
7. Atomic ready state, generated wall/floor/collision, actual Pawn traversal, SaveGame restart ve offline retention kontrollerini shape-first kaynakla tekrar çalıştır. Düşük clear width seçilmişse geometry-only export ile gameplay readiness farklı sonuç verebilir; Play için geçersiz agent clearance açıkça bloklanır.
8. Annotation/training ingestion otomatik başlatılmaz. User-approved design sizes, image-ground-truth dimensions olarak eğitim/evaluation'a girmez. User corrections uygun curation ile yalnızca geometry/topology supervision adayıdır.
9. Eski strict-measurement regression fixture'larını koru. Step 13 OCR/numeric accuracy skorlarını shape-first başarı skoru diye tekrar kullanma; geometry, attachment, exact topology, intervention effort ve design validity için yeni evaluation raporu çıkar.
10. Architecture/usage/convention belgelerini yeni default için güncelle; local launcher ve error recovery akışını doğrula. Bu aşamalar hosted SaaS, authentication/payments, arbitrary polygons veya multi-floor kapsamı eklemez.

**Zorunlu acceptance matrisi:**

| Senaryo | Beklenen sonuç |
| --- | --- |
| Sayısız, dalgalı 2–6 room çizimi | Shape proposals; kullanıcı düzeltmesi + tüm size suggestions |
| Eski, üzerinde sayılar olan çizim | Numeric OCR çağrısı olmadan aynı shape-first akış; sayılar size input değil |
| Grid, stray ticks, accidental gap | Fazladan passage kesinleştirilmez; uncertainty/edit imkanı |
| Shared wall'da iki door | İki interval, ayrı offsets; unique physical wall |
| Birden fazla corridor, T junction, cycle | Rectangular segmentler ve tutarlı bağlantılar korunur |
| Room resize / door width edit | Bağlı preview güncellenir veya açıklanabilir conflict çıkar; user lock değişmez |
| AI boş/timeout/unavailable | Image korunur, manual plan authoring/export devam eder |
| Eski preview/revision ile export | Stale istek reddedilir; yeni draft kaybolmaz |
| Confirm → download → Unreal | Aynı source/revision, doğru geometry + collision |
| Gameplay Start→Goal | Gerçek Pawn Goal'a ulaşır; başarısız clearance'da Play bloklanır |
| Save/restart/offline | Onaylanmış design ve provenance korunur; önceki valid level yarım değişmez |
| Aynı resmin resize/crop türevi | Görünür topology aynıysa design scale önerisi değişmez; içerik kesilmişse re-review |

**Teslim / bitiş koşulu:** Gerçek web upload→AI proposals→manual corrections→editable suggestions→explicit confirmation→validated download→Unreal/runtime akışı doğrulanmış; fresh restart, negative fixtures ve source/provenance sınırları test edilmiş. Otomatik algılamanın ölçülen başarısı ve manual fallback sonuçları ayrı raporlanmış. Core teslimin tamamlanması, kusursuz AI algılama veya genel kullanıma hazır hosted servis iddiası değildir.

## Implementation sırası ve kapsam kontrolü

| İstek | Tamamlanacak kapsam |
| --- | --- |
| “Yeni guide Step 1” | Yeni contract, policy ve compatibility; model training/UI değişikliği yok |
| “Yeni guide Step 2” | Gerçek AI geometry adapter, wavy recovery ve ölçülen pilot; sayı okuma yok |
| “Yeni guide Step 3” | Joint suggestions, editable locks ve geometric consistency |
| “Yeni guide Step 4” | Profesyonel web workspace ve gerçek editing akışı |
| “Yeni guide Step 5” | Confirm/export/runtime, persistence ve uçtan uca testler; yeni default'a geçiş |

Her aşama sonunda değişen davranış, test kanıtı, kalan belirsizlik ve sonraki aşamaya hazır olma durumu raporlanır. İlgisiz model/asset/dataset değişiklikleri yapılmaz. Mevcut 50 original drawing ve annotations korunur.

## Bu planın dayandığı mevcut proje kanıtları

- [Product architecture](product_architecture.md): mevcut Python/browser/Unreal sınırı ve tamamlanan core.
- [Drawing convention v1](drawing_convention_v1.md): shared wall, door ticks ve rectangular segment kuralları; sayı zorunluluğu yeni modda kaldırılacak.
- [Geometry/VLM pilot](geometry_multimodal_pilot_results_2026_10_19.md): mevcut local VLM'nin geometry için doğrulanmış bir çözüm olmadığı ve veri sınırları.
- [Topology review](step08_topology_review.md), [metric review](step10_metric_review.md): kullanılabilecek persistence/interaction parçaları ve değişecek ölçüm akışı.
- [Data 41–50 annotation review](../Data/annotation_review_41_50.md): multi-door, T junction, cycle ve corridor interface fixture'ları; eski physical labels yeni mode'da observation olarak kullanılmayacak.
- [Packaged runtime](step14_packaged_runtime.md): korunacak canonical geometry, runtime ready-state ve SaveGame entegrasyonu.
