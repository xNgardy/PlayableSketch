from pathlib import Path
import json
import zipfile

root = Path.cwd()
old = root / 'outputs/day4'
out = root / 'outputs/authoring-validation'
out.mkdir(parents=True, exist_ok=True)
mapping = {
    'PlayableSketchDay4Tests': 'PlayableSketchAuthoringValidationTests',
    'FPlayableSketchDay4AutomationTest': 'FPlayableSketchAuthoringValidationAutomationTest',
    'TestDay4Validation': 'TestAuthoringValidation',
    'PlayableSketch.Day4.Validation': 'PlayableSketch.Authoring.Validation',
    'Day 4 test resize': 'Authoring validation test resize',
    'Day 4 tests finished': 'Authoring validation tests finished',
}

def rename(text):
    for before, after in mapping.items():
        text = text.replace(before, after)
    return text

manifest = json.loads((old / 'manifest.json').read_text(encoding='utf-8'))
changed = []
for item in manifest:
    original_path = item['path']
    source = old / original_path
    if Path(original_path).name in ('PlayableSketchLevelActor.h', 'PlayableSketchLevelActor.cpp'):
        source = root / original_path
    original = source.read_text(encoding='utf-8-sig')
    content = rename(original)
    item['path'] = rename(original_path)
    destination = out / item['path']
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content.rstrip() + '\n', encoding='utf-8')
    assert 'day' not in content.lower(), item['path']
    assert '//' not in content and '/*' not in content, item['path']
    if content != original or original_path != item['path']:
        changed.append(item)

assert len(changed) == 4
guide = '''# PlayableSketch — Authoring Validation testleri

Test adları yaptıkları işi anlatacak şekilde düzenlendi. Authoring, Room ve Connection verisini düzenleme işlemlerini ifade eder. Validation, bu düzenlemelerin geçerli bir tasarım üretip üretmediğini kontrol eder. Testlerin davranışı aynı kaldı; dosya, sınıf, fonksiyon, include, log ve automation adları birlikte değiştirildi.

## Uygulama

1. Unreal Editor'ı kapat.
2. Aşağıdaki iki Actor dosyasının içeriğini tam olarak değiştir.
3. İki test dosyasını aşağıdaki yeni dosya adlarıyla oluştur. Önceki isimlerle oluşturduğun bu test dosyaları varsa, onların yerine bu dosyaları kullan; iki sürümü Source altında birlikte bırakma.
4. Visual Studio'da Development Editor / Win64 yapılandırmasıyla build al. Visual Studio dosya listesini yenilemen gerekiyorsa .uproject üzerinden Generate Visual Studio project files çalıştır.
5. Unreal Editor'ı aç. Level Actor'ın Details panelinde PlayableSketch > Tests altında Test Authoring Validation düğmesine bas.
6. Output Log'da `Authoring validation tests finished: Failures=0` sonucunu kontrol et. Automation penceresindeki test yolu `PlayableSketch.Authoring.Validation` olur.

Bu isim değişikliği yalnızca aşağıdaki dört dosyayı etkiliyor. Source dosyaların otomatik değiştirilmedi; implementasyonu sen yapacaksın. Zip içinde önceki tam uygulama paketinin 14 dosyası da yeni isimlerle bulunuyor. Önceki paketi tamamen uyguladıysan yalnızca bu dört dosyayı güncellemen yeterli.

| Öğe | Yeni ad |
|---|---|
| Test dosyaları | PlayableSketchAuthoringValidationTests.h / .cpp |
| Test sınıfı | FPlayableSketchAuthoringValidationTests |
| Actor fonksiyonu | TestAuthoringValidation |
| Editör düğmesi | Test Authoring Validation |
| Automation testi | PlayableSketch.Authoring.Validation |

## Kontrol

Paketin dosya ve sembol adları, include yolları ve automation adı birlikte kontrol edildi. Kodda takvim aşaması belirten ad veya yorum satırı bulunmuyor. Önceki paket izole projede UE 5.7.4 Editor build ve 21 test kontrolünden geçmişti. Bu isim değişikliğinden sonra build ve Unreal testleri tekrar çalıştırılmadı.

## Değişen dört dosyanın tam son halleri

'''
for item in changed:
    content = (out / item['path']).read_text(encoding='utf-8')
    guide += f"### {item['path']}\n\n```cpp\n{content}```\n\n"

test_h = out / 'Source/PlayableSketch/Public/Validation/Tests/PlayableSketchAuthoringValidationTests.h'
test_cpp = out / 'Source/PlayableSketch/Private/Validation/Tests/PlayableSketchAuthoringValidationTests.cpp'
actor_h = out / 'Source/PlayableSketch/PlayableSketchLevelActor.h'
actor_cpp = out / 'Source/PlayableSketch/PlayableSketchLevelActor.cpp'
assert 'class PLAYABLESKETCH_API FPlayableSketchAuthoringValidationTests' in test_h.read_text()
assert 'bool FPlayableSketchAuthoringValidationTests::Run()' in test_cpp.read_text()
assert 'void TestAuthoringValidation();' in actor_h.read_text()
assert 'void APlayableSketchLevelActor::TestAuthoringValidation()' in actor_cpp.read_text()
assert '#include "Validation/Tests/PlayableSketchAuthoringValidationTests.h"' in actor_cpp.read_text()
assert '#include "Validation/Tests/PlayableSketchAuthoringValidationTests.h"' in test_cpp.read_text()

(out / 'Degisen_Dosyalar_Tam_Kodlar.md').write_text(guide, encoding='utf-8')
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
with zipfile.ZipFile(out / 'PlayableSketch_Authoring_Validation_Kod_Paketi.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
    for item in manifest:
        bundle.write(out / item['path'], item['path'])
    bundle.write(out / 'manifest.json', 'manifest.json')
    bundle.write(out / 'Degisen_Dosyalar_Tam_Kodlar.md', 'Degisen_Dosyalar_Tam_Kodlar.md')
print(json.dumps({'source_files': len(manifest), 'changed_files': [i['path'] for i in changed], 'naming_checks': 'passed'}, indent=2))
