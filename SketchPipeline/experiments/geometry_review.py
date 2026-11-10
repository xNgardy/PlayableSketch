import html
import json
import random
import numpy as np
from PIL import Image
from SketchPipeline.experiments.geometry_study import OUT, ARMS, MANIFEST, samples, summary
from SketchPipeline.preprocessing.prepare import prepare
from SketchPipeline.synthetic.augment import read

SCRIPT = "\nconst cases=DATA;\nlet index=0, segments=[],log=[],running=false,started=0,activeStart=0,activeMs=0,drag=null;\nconst $=id=>document.getElementById(id), canvas=$('canvas'),ctx=canvas.getContext('2d'),source=new Image();\nlet records=JSON.parse(localStorage.getItem('geometry-review-v1')||'[]');\nfunction redraw(){\n ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);\n if($('background').checked&&source.complete&&source.naturalWidth){ctx.globalAlpha=.3;ctx.drawImage(source,0,0,canvas.width,canvas.height);ctx.globalAlpha=1;}\n for(const s of segments){ctx.strokeStyle=s.kind==='wall'?'#087c80':'#df342b';ctx.lineWidth=s.kind==='wall'?3:6;\n ctx.beginPath();ctx.moveTo(...s.a);ctx.lineTo(...s.b);ctx.stroke();}\n $('counts').textContent=`${segments.filter(s=>s.kind==='wall').length} wall segments; ${segments.filter(s=>s.kind==='opening').length} opening intervals; ${log.length} edits`;\n}\nfunction load(){if(running)return;const c=cases[index];segments=structuredClone(c.segments);log=[];drag=null;\n canvas.width=c.width;canvas.height=c.height;source.onload=redraw;source.src=c.source;$('original').src=c.source;\n $('case').textContent=`${index+1}/${cases.length}: ${c.label}`;$('state').textContent='Ready. Start before editing. Arm identity is hidden; no ground truth is supplied.';redraw();}\nfunction pos(e){const r=canvas.getBoundingClientRect();return[(e.clientX-r.left)*canvas.width/r.width,(e.clientY-r.top)*canvas.height/r.height];}\nfunction dist(p,s){const v=[s.b[0]-s.a[0],s.b[1]-s.a[1]],d=v[0]**2+v[1]**2,t=d?Math.max(0,Math.min(1,((p[0]-s.a[0])*v[0]+(p[1]-s.a[1])*v[1])/d)):0;return Math.hypot(p[0]-s.a[0]-t*v[0],p[1]-s.a[1]-t*v[1]);}\nfunction nearest(p){let best=null;segments.forEach((s,i)=>{const d=dist(p,s);if(d<18&&(!best||d<best.d))best={i,d};});return best;}\ncanvas.onpointerdown=e=>{if(!running)return;canvas.setPointerCapture(e.pointerId);const p=pos(e),tool=$('tool').value;\n if(tool==='delete'){const n=nearest(p);if(n){log.push({action:'delete',segment:segments[n.i],ms:performance.now()-started});segments.splice(n.i,1);redraw();}return;}\n if(tool==='move'){let best=null;segments.forEach((s,i)=>['a','b'].forEach(end=>{const d=Math.hypot(p[0]-s[end][0],p[1]-s[end][1]);if(d<20&&(!best||d<best.d))best={i,end,d};}));if(best)drag={...best,before:structuredClone(segments[best.i]),tool};return;}\n drag={p,tool};};\ncanvas.onpointerup=e=>{if(!running||!drag)return;const p=pos(e),d=drag;drag=null;\n if(d.tool==='move'){segments[d.i][d.end]=p;log.push({action:'move_endpoint',before:d.before,after:structuredClone(segments[d.i]),ms:performance.now()-started});}\n else if(d.tool==='box_delete'){const lo=[Math.min(d.p[0],p[0]),Math.min(d.p[1],p[1])],hi=[Math.max(d.p[0],p[0]),Math.max(d.p[1],p[1])];\n const removed=segments.filter(s=>[s.a,s.b].every(q=>q[0]>=lo[0]&&q[0]<=hi[0]&&q[1]>=lo[1]&&q[1]<=hi[1]));segments=segments.filter(s=>!removed.includes(s));log.push({action:'box_delete',removed,ms:performance.now()-started});}\n else if(Math.hypot(p[0]-d.p[0],p[1]-d.p[1])>2){const s={kind:d.tool,a:d.p,b:p};segments.push(s);log.push({action:'add',segment:structuredClone(s),ms:performance.now()-started});}redraw();};\n$('start').onclick=()=>{if(running)return;running=true;started=performance.now();activeStart=document.hidden?0:started;activeMs=0;$('state').textContent='Recording edits and time. Finish only when the pixel topology is corrected. No cm inference.';};\ndocument.addEventListener('visibilitychange',()=>{if(!running)return;const now=performance.now();if(document.hidden&&activeStart){activeMs+=now-activeStart;activeStart=0;}else if(!document.hidden)activeStart=now;});\n$('finish').onclick=()=>{if(!running)return;const now=performance.now();if(activeStart)activeMs+=now-activeStart;\n records.push({schema_version:'playablesketch-geometry-review-benchmark/1.0',case_key:cases[index].key,label:cases[index].label,\n wall_clock_seconds:(now-started)/1000,visible_tab_seconds:activeMs/1000,edits:structuredClone(log),corrected_segments:structuredClone(segments),\n completed_at:new Date().toISOString(),ground_truth_verified:false,metric_layout_accepted:false});\n localStorage.setItem('geometry-review-v1',JSON.stringify(records));running=false;$('state').textContent='Review saved locally. Export results to preserve actual timings. Geometry correctness still needs independent verification.';};\n$('prev').onclick=()=>{if(!running){index=(index+cases.length-1)%cases.length;load();}};\n$('next').onclick=()=>{if(!running){index=(index+1)%cases.length;load();}};\n$('background').onchange=redraw;\n$('export').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(records,null,2)],{type:'application/json'}));a.download='geometry-review-timings.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};\nload();\n"


def build():
    report = summary()
    cards = []
    benchmark = []
    mapping = {}
    rng = random.Random(20261019)
    for sample in samples():
        sid = sample["id"]
        dest = OUT / "review_sources" / f"{sid}.jpg"
        dest.parent.mkdir(exist_ok=True, parents=True)
        if not dest.exists():
            images, prep = prepare(
                (MANIFEST.parent / sample["image_path"]).resolve(), max_side=1600
            )
            Image.fromarray(images["color"]).save(dest, quality=94)
        arms = ARMS.copy()
        rng.shuffle(arms)
        for n, arm in enumerate(arms):
            directory = OUT / arm / sid
            if not (directory / "metrics.json").exists():
                continue
            record = read(directory / "metrics.json")
            w = read(directory / "working.json")
            m = record["metrics"]["openings"]
            cards.append(
                f"""<article><h3>{html.escape(sid)} · {arm}</h3><p>TP {m['true_positive']}, predicted {m['predicted']}, reference {m['reference']}; {w['duration_seconds']:.2f}s; {record['status']}</p><a href="{arm}/{sid}/preview.jpg"><img loading="lazy" src="{arm}/{sid}/preview.jpg"></a></article>"""
            )
            width, height = w["preprocessing"]["working_size_px"]
            rotation = np.radians(w["topology"]["rotation_degrees_removed"])
            c, s = (np.cos(rotation), np.sin(rotation))
            matrix = np.array([[c, -s], [s, c]])
            center = np.array([width / 2, height / 2])

            def point(p):
                return ((np.asarray(p) - center) @ matrix.T + center).tolist()

            segments = [
                dict(kind="wall", a=point(e["a"]), b=point(e["b"]))
                for e in w["topology"]["wall_graph"]["edges"]
                if e["kind"] == "physical_wall"
            ]
            segments += [
                dict(kind="opening", a=g["start"], b=g["end"])
                for g in w["gaps"]
                if g["role"] == "opening_candidate"
            ]
            key = f"{sid}-variant-{n + 1}"
            mapping[key] = arm
            benchmark.append(
                dict(
                    key=key,
                    label=f"{sid} · anonymous variant {n + 1}",
                    source=f"review_sources/{sid}.jpg",
                    width=width,
                    height=height,
                    segments=segments,
                )
            )
    (OUT / "review-arm-mapping.json").write_text(json.dumps(mapping, indent=2) + "\n")
    page = '<!doctype html><meta charset="utf-8"><title>Geometry pilot comparison</title><style>body{font:15px system-ui;margin:24px;background:#f2f3f5;color:#18202b}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:16px}article{background:white;padding:12px;border-radius:8px}img{width:100%}td,th{padding:8px;text-align:right;border-bottom:1px solid #ddd}th:first-child,td:first-child{text-align:left}</style><h1>Geometry validation pilot</h1><p>19 validation originals. Cached OCR shared by all arms. Timings exclude OCR/model load. Pixel proposals, no metric acceptance.</p><p><a href="review_benchmark.html">Timed editing benchmark</a> · <a href="report.json">Full report</a></p><p>For blinded timing, complete assigned editing cases before inspecting this gallery. Human correction times are pending; machine error counts are not elapsed time.</p>'
    page += "<table><tr><th>Arm</th><th>Evaluated / expected</th><th>Failed</th><th>Opening P</th><th>Opening R</th><th>Opening F1</th><th>Exact topology</th><th>p50 sec</th></tr>"
    for arm in ARMS:
        r = report[arm]["all"]
        if not r.get("evaluated"):
            continue
        op = r["openings"]
        denominator = op["predicted"] + op["reference"]
        op["f1"] = 2 * op["true_positive"] / denominator if denominator else None
        percent = lambda x: "—" if x is None else f"{100 * x:.1f}%"
        page += f"<tr><td>{arm}</td><td>{r['evaluated']}/{r['expected']}</td><td>{r['failed']}</td><td>{percent(op['precision'])}</td><td>{percent(op['recall'])}</td><td>{percent(op['f1'])}</td><td>{r['exact_topology']['correct']}/{r['exact_topology']['scorable']}</td><td>{r['inference_seconds']['p50']:.2f}</td></tr>"
    page += "</table><main>" + "".join(cards) + "</main>"
    (OUT / "index.html").write_text(page)
    ui = '<!doctype html><meta charset="utf-8"><title>Timed geometry review</title><style>body{font:15px system-ui;margin:18px;color:#17212c}button,select{font:inherit;margin:4px;padding:8px}main{display:grid;grid-template-columns:1fr 1fr;gap:15px}img,canvas{width:100%;border:1px solid #ddd;touch-action:none}header{position:sticky;top:0;background:white;padding:6px;z-index:1}p{max-width:1050px}</style><header><h2 id="case"></h2><button id="prev">Previous</button><button id="next">Next</button><button id="start">Start timer</button><button id="finish">Finish review</button><button id="export">Export actual timings</button><select id="tool"><option value="delete">Delete nearest</option><option value="move">Move endpoint</option><option value="wall">Draw wall</option><option value="opening">Draw opening</option><option value="box_delete">Box delete (fully enclosed)</option></select><label><input id="background" type="checkbox">Source under overlay</label><p id="state"></p><p id="counts"></p></header><p>Left: original working image. Right: editable pixel hypotheses, walls teal and openings red. Start, correct the geometry, then Finish. Drag to draw or move an endpoint; click to delete. Box delete removes segments with both endpoints in the dragged box. Arm identities are hidden. Tab-hidden time is separately excluded from visible-tab duration; distractions in a visible tab are still counted. Exports remain unverified review artifacts.</p><main><section><h3>Source</h3><img id="original"></section><section><h3>Editable hypotheses</h3><canvas id="canvas"></canvas></section></main><script>'
    ui += (
        SCRIPT.replace("DATA", json.dumps(benchmark, separators=(",", ":")).replace("<", "\\u003c"))
        + "</script>"
    )
    (OUT / "review_benchmark.html").write_text(ui)


if __name__ == "__main__":
    build()
