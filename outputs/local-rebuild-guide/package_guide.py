from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import difflib
import hashlib
import json

folder = Path(__file__).resolve().parent
root = folder.parents[1]
files = sorted((folder / 'Source').rglob('*'))
files = [p for p in files if p.is_file()]
assert len(files) == 6
guide = folder / 'Rehber.md'
text = guide.read_text(encoding='utf-8').split('<!-- FULL_SOURCE_START -->')[0].rstrip()
text += '''

Doğrulama: Paket kaynakları ana Source'a uygulanmadan ayrı proje kopyasında UE 5.7.4, Development Editor / Win64 hedefinde derlendi. Build başarılı. `PlayableSketch.Geometry.LocalRebuild` otomasyon testi başarılı (10 bağımsız edit ve ek fallback/cleanup/engel kontrolleri). Çalıştırma NullRHI ile yapıldı; görsel kalite, gerçek Pawn ile fizik geçişi, kendi assetlerinde Undo/Redo ve save/reopen kontrollerini uygulamadan sonra sen yapmalısın. Ham sonuç `test-result.json` dosyasında.

<!-- FULL_SOURCE_START -->
'''
patch = []
manifest = {}
for file in files:
    relative = file.relative_to(folder).as_posix()
    source = file.read_text(encoding='utf-8')
    title = 'DEĞİŞTİR' if (root / relative).exists() else 'YENİ'
    text += f'\n### {title}: `{relative}`\n\n```cpp\n{source.rstrip()}\n```\n'
    previous = (root / relative).read_text(encoding='utf-8-sig') if (root / relative).exists() else ''
    patch.extend(difflib.unified_diff(previous.splitlines(True), source.splitlines(True),
        fromfile=('a/' + relative) if previous else '/dev/null', tofile='b/' + relative))
    manifest[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
    assert file.read_bytes() == (folder / 'build-check' / relative).read_bytes(), relative
guide.write_text(text, encoding='utf-8')
(folder / 'Changes.patch').write_text(''.join(patch), encoding='utf-8')
report = json.loads((folder / 'build-check/test-report/index.json').read_text(encoding='utf-8-sig'))
assert report['succeeded'] == 1 and report['failed'] == 0, report
(folder / 'test-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
(folder / 'verification.json').write_text(json.dumps({
    'engine': 'UE 5.7.4', 'target': 'PlayableSketchEditor Win64 Development',
    'build': 'Succeeded', 'automation': 'PlayableSketch.Geometry.LocalRebuild',
    'automation_result': 'Success', 'independent_edit_cases': 10,
    'headless': True, 'main_project_source_modified': False,
    'source_sha256': manifest,
    'manual_checks_remaining': ['PIE pawn passage and collision', 'Scene visual check', 'Undo/Redo', 'Save/reopen']
}, ensure_ascii=False, indent=2), encoding='utf-8')
with ZipFile(folder / 'PlayableSketch_LocalRebuild_Paketi.zip', 'w', ZIP_DEFLATED) as archive:
    for file in files + [guide, folder / 'Changes.patch', folder / 'verification.json', folder / 'test-result.json']:
        archive.write(file, file.relative_to(folder).as_posix())
print(json.dumps({'files': len(files), 'guide_lines': len(text.splitlines()),
    'zip_bytes': (folder / 'PlayableSketch_LocalRebuild_Paketi.zip').stat().st_size,
    'automation': report['succeeded'], 'failed': report['failed']}, ensure_ascii=False))
