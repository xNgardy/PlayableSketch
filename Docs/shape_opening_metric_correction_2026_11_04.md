# Opening metriği düzeltmesi — 4 Kasım 2026

Önceki shape-first pilot ve decoder raporlarında insan opening referansları
oluşturulurken annotation `gaps` dizisinin bütün elemanları sayılmıştı. Data 41'deki
`g004`, kaynak annotation'da `kind: incidental`, `opening_candidate_id: null` ve
“Small unmarked corner break; not a door” olarak etiketli. Buna rağmen önceki
18 opening paydasına dahil edilmişti. Bu bir skorlayıcı hatasıydı.

`pilot.human_reference` ve yeni yapısal referans okuyucu artık yalnızca `door` ve
`open_passage` türlerini opening referansı sayıyor. Test, incidental kırığın ne
pozitif marker gözetimine ne de opening referansına girdiğini doğruluyor.

Aynı altı çizim için doğru payda **16 door + 1 open passage = 17 opening**.
Önceki seçilmiş decoder tahminleri değişmedi: 6 doğru, 6 öneri. Düzeltilmiş recall
**6/17 (%35,3)**; **11 gerçek opening eksik**. 6/18→6/17 farkı bir model kazanımı
olarak raporlanmamalı. Görsel/annotation/accepted dosyaları değiştirilmedi.

Eski JSON raporları ve deney çıktıları tarihsel kayıt olarak korunuyor; bu not
onların insan opening paydasını geçersiz kılar. Yeni sonuçlar
`reference_policy_version: structural-openings/2.0` ile kaydedilir. İnsan exact
topology hâlâ bağımsız doğrulanmış bir ölçüm değildir.

Düzeltilmiş eksik listesi ve neden galerisi:
`Saved/ShapeFirst/human_adaptation/v1/error_review_corrected/`.

| Neden | Eksik opening |
| --- | ---: |
| Bağlı region bulunamadı | 8 |
| Paired tick ink kontrolünde elendi | 1 |
| Gap/support aramasında aday kaçtı | 2 |
| **Toplam** | **11** |

Neden ataması yaklaşık referans geometrisi ve kaydedilmiş decoder kanıtı üzerinden
teşhistir; model inference'ına referans bilgi verilmedi.
