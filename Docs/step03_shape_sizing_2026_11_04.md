# Shape-first Step 3 — ortak boyutlandırma, düzenleme ve canonical önizleme

Tarih: 4 Kasım 2026. Rehberdeki Step 3 çekirdeği ve API teslim edildi.
Profesyonel kullanıcı workspace'i (Step 4) ve onaylı export/Unreal zinciri
(Step 5) bu teslimin parçası değildir. Step 2 algılama hataları açık kalır.

## Davranış

- Ölçü girmeden, room/corridor/door/open-interface için başlangıç boyutları oluşur.
- En büyük yorumlanmış oda için 20 m² referans alanı bir **tasarım tercihi** olarak
  kullanılır; diğer şekil oranları ve aralıklar soft preference olur. Örneğin
  200×160 ve 120×160 iki oda yaklaşık 500×400 ve 300×400 cm önerilir.
- Corridor width 200, door clear width 120 cm başlangıcıdır. Duvar 20/300, door
  height 220 ve floor thickness 20 cm açık uygulama konfigürasyonudur. Floor
  mevcut runtime varsayımından yapılandırılır; görüntüden çıkarılmaz.
- `design_scale` 0.1–10 arasında tüm başlangıç tasarım ölçeğini değiştirir.
- Boyutlar ortak bir konveks çözümde hesaplanır. Aynı gerçek duvar ve T-junction
  koordinatı bir kez çözülür. Salt aynı hizada duran bağlantısız odalar bağımsız
  boyutlandırılabilir. Pozitif noded wall uzunlukları ve region non-overlap hard
  koşuldur; dış sınır tek rectangle'a zorlanmaz.
- Öneriler soft hedeflerdir. Door önerisi kullanıcı değiştirmedikçe 120 cm olarak
  korunur; gerekirse destekleyen duvar büyür. Kullanıcı boyutları (kilit açıkken
  de) sessizce yeniden önerilmez. Lock mevcut değeri hard tutar; reset tekrar
  öneri/preset tercihine döner. Keep proportions (`aspect_locks`) hard oran tutar.
- Width/depth/length, door clear width ve near-edge offset düzenlenebilir. Global
  wall/floor/height ayarları vardır. Metre/milimetre girişleri cm'ye çevrilir;
  bool, NaN/Infinity, negatif/aşırı ve yanlış türde değerler reddedilir.
- Strict v1 canonical contract tek global door/wall height bekler. Bağımsız bir
  opening height bununla çelişirse açık height_conflict döner; parser gevşetilmez.
- Open passage clear width = shared supporting span - wall thickness; near edge
  thickness/2. Bu, bölümler arasındaki fiziksel açıklığı devamlı tutar. İmkânsız
  width/offset override durumunda passage silinmez, conflict raporlanır.
- Aynı shared wall üzerinde çoklu door ayrı kalır; interval sırası ve non-overlap
  birlikte çözülür. Near-edge reference/end direction ve global 0/90/180/270
  orientation canonical positive-axis center offset'e doğru çevrilir.

## Kullanıcı değişiklikleri ve başarısızlık

Her adjustable stable ID, origin, lock, previous suggestion ve revision binding
saklar. Kullanıcı override'ı `user_override` kalır; öneriyi seçmek onu görüntü
ölçümüne dönüştürmez. `size_assumptions`, `suggestion_adjustments` ve `changes`
alanları başlangıç tercihini, çözümde değişenleri ve before/after değerleri açıklar.

Çelişkide status `needs_attention`, kullanıcı değerleri draft'ta kalır; preview
son geçerli plandır ve `preview_is_stale=true`. Geçerli plan yoksa preview null.
İlgili entity ID'leri ve reset/unlock/review önerileri raporlanır. Door silme,
user lock'u değiştirme veya sahte valid fallback yoktur.

Topology değişince önceki değerler stale olur. Silinmiş entity'nin değerleri
`orphaned_values` sidecar'ında korunur. Salt eski ID hâlâ var diye binding
aktarılmaz. Kullanıcı yeni planı gözden geçirdikten sonra açık `reset_bindings`
isteğiyle yeni öneriler oluşturulabilir; önceki girdiler journal'da ve
`discarded_bindings` alanında korunur.

## API

Mevcut local shape server üzerinde:

- `GET /shape-jobs/{id}/sizing`: son sizing sonucu veya not_sized.
- `POST /shape-jobs/{id}/sizing`: proposal / recompute / edits / lock / reset.
- `GET /shape-jobs/{id}/sizing-plan`: current veya stale last-valid planın SVG'si.

POST mevcut `X-Shape-Token` ve local-origin kontrollerini kullanır. İlk örnek:

```json
{
  "base_revision_id": "CURRENT_TOPOLOGY_REVISION",
  "base_sizing_revision_id": null,
  "request": {"use_suggested_sizes": true}
}
```

Sonraki editte `base_sizing_revision_id`, dönen authoring revision olmalı:

```json
{
  "base_revision_id": "CURRENT_TOPOLOGY_REVISION",
  "base_sizing_revision_id": "CURRENT_SIZING_REVISION",
  "request": {
    "aspect_locks": ["ROOM_ID"],
    "edits": [{"entity_id":"ROOM_ID", "parameter":"width_cm", "action":"set", "value":8, "unit":"m", "locked":true}]
  }
}
```

Action `lock`, `unlock` veya `reset` için value gerekmez. `settings` konfigürasyonu
uygulama varsayımlarını kurar; mevcut kullanıcı tercihini değiştirmek için `edits`
kullanılır. `use_suggested_sizes` toplu seçim kaydıdır; topology acceptance veya
export izni değildir. Teknik ID/revision alanları Step 4 UI tarafından yönetilir.

Stale topology/sizing revision 409 ile reddedilir. Sonuçlar atomic pointer ve ayrı
immutable journal kayıtlarında saklanır. Reopen aynı user choices/preview'ı getirir.
Boyut tercihi bulunan job retry ile overwrite edilmez; yeni job gerekir. Kaynak
AI önerileri ve manuel topology draft'ı ayrı kalır.

## Canonical adapter ve doğrulama

`sizing_adapter.py` strict `playablesketch-layout/1.0` **draft** oluşturur.
Vertices/walls/CCW region boundaries, typed owners, ayrı opening/passages ve
local offset'ler gerçek geometriye göre oluşturulur. T junction noding,
non-overlap, opening containment ve v1 settings mevcut `validate_document`
ile doğrulanır. Validator/parser alanları veya kuralları gevşetilmedi.

`observation_document_id` gerçek shape-authoring document ID'sidir; OCR
observations dosyası üretilmez. Evidence ID'leri boş, computed provenance derived,
settings configured; tam image/size provenance authoring sidecar'da kalır.
Draft kind/review pending ve exportable=false korunur. Engine geometry ve
navigation not_run; Unreal başarı iddiası yoktur.

Yeni policy `shape-sizing/2.0`; authoring schema bilinen 1.0 ve 2.0 policy'lerini
kabul eder, diğer alanların strict yapısı korunur. Eski Step 1 fixtures geçerlidir.
Near-edge conversion varsayılanı hâlâ strict'tir. Adapter, altı ondalık yazımın
boundary kalıntıları için 0.00001 cm tolerans kullanır; mevcut metric validator
0.001 cm toleransından daha sıkıdır. Büyük taşmalar bununla geçmez.

## Solver ve bağımlılıklar

Numpy tabanlı equality elimination + dual projection ile weighted least-squares
çözülür. Preset/ratio/spacing hedefleri soft, user choices ve topology hard'dır.
İmkânsız veya iterasyon limitli durum valid ilan edilmez. Ek solver paketi,
model indirme veya network gerekmez; mevcut yerel Python ortamı kullanılır.

## Test ve örnek sonuçları

- **114 benzersiz test geçti:** ilgili suite 112 + iki gerçek loopback HTTP testi.
  Aynı testler tekrar sayılmadı. HTTP için yalnızca local bind sandbox izni kullanıldı.
- Yeni çekirdek 24, sizing job/API 5 test: automatic defaults, resize/crop invariance,
  numbered source independence, user override/units, lock/reset, aspect lock,
  conflicting shared dimensions, two doors, offset conflict, large door growth,
  reversed references/rotation, corridor bend, cycle, aligned disconnected rooms,
  topology stale/reset, settings/height, bad input, pending acceptance ve strict
  adapter. Persistence/restart, stale-request 409 ve HTTP token/SVG de doğrulandı.
- 50 insan + 60 sentetik kaydedilmiş AI topology'sinin **110/110**'u metric-valid
  canonical preview üretti. Her biri pending draft; hiçbirisi accepted export değil.
- Bu sayı perception başarısı değildir. Fazla/yanlış region veya eksik connection
  içeren bir plan da kendi içinde geçerli boyutlandırılabilir. Kaynaklar geçmişte
  incelenmiş development verisi; yeni-yazar kanıtı ve kullanıcı düzeltme süresi yok.
- v1–v3 ara sonuçları korundu. Üç ilk boundary serialization hatası düzeltildi;
  son v4, gerçek structural equality gruplarıyla yeniden 110/110 doğrulandı.
- `edit-demo/`: suggested → 8 m custom width → 20 cm depth conflict preserves
  preview → reset recovers. Core input documents mutate edilmez.
- Data 25 ve 48 SVG'leri yerel PNG'ye render edilip görsel olarak incelendi.
  Profesyonel workspace browser etkileşimi yapıldı denmiyor.
- Model, default lock, kaynak görüntüler ve accepted tasarımlar değiştirilmedi.
  İlgisiz mevcut Unreal/C++ değişikliklerine dokunulmadı.

## Kullanım ve teslim dosyaları

CLI, yeni bir output klasörü kullanır:

```sh
PYTHONDONTWRITEBYTECODE=1 Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.sizing --input AUTHORING.json --output Saved/ShapeFirst/sizing/new-preview
PYTHONDONTWRITEBYTECODE=1 Saved/Training/v1/python/bin/python -m SketchPipeline.shape_authoring.evaluate_sizing --output Saved/ShapeFirst/sizing/new-evaluation
```

CLI `--request REQUEST.json` ile aynı request alanlarını kabul eder. Sonuçlar
result.json, authoring.json ve canonical-preview.json olarak yazılır.

Nihai kanıt: `Saved/ShapeFirst/sizing/v4/` altında report.json, verification.json,
source_snapshot/, tests.log, http-tests.log, gallery.html, edit-demo/ ve her
örneğin SVG/JSON önizlemesi. Arayüzde yeni upload otomatik sizing çalıştırması ve
boyut inspector'ı Step 4'te bu API'ye bağlanacak; mevcut teknik review ekranı
profesyonel Step 4 workspace'i sayılmıyor. Step 5 accepted snapshot/export/import
hattı ayrıca tamamlanmalıdır.
