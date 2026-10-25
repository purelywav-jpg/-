"""shopping-shorts pipeline: voice -> build (mp4 + CapCut draft).

usage:
  python build_shorts.py voice  config.json   # TTS (Kanna) + speed-up + whisper word timings + caption preview
  python build_shorts.py build  config.json   # scenes + thumbnail + captions + mp4 + CapCut draft

config.json (all paths absolute, use forward slashes or raw strings):
{
  "name": "desk_shorts_v1",                 # CapCut draft name (ASCII)
  "workdir": "C:/CapCutAssets/desk_ad",     # staging dir (ASCII path, no spaces)
  "src_dir": "C:/Users/IdeaPad/Desktop/클로드 영상편집 자동화/쇼핑쇼츠/desk",
  "script": "문장1. 문장2? ...",              # narration, sentences end with . ? ~
  "voice_id": "5I7B1di44aCL15NkP0jn",       # optional, default Kanna
  "post_tempo": 1.06,                       # optional extra speed-up after ElevenLabs (API caps at 1.2)
  "scenes": [                               # in narration order
    {"clip": "7244292", "start": 4.5, "cut_at": "그런데",        "crop": [0, 0.83]},
    {"clip": "Powerful", "start": 6.0, "cut_at": 9.54},          # cut_at: seconds OR text found in a caption chunk (cut = that chunk's start)
    {"clip": "7276754", "start": 6.0}                             # last scene: no cut_at
  ],
  "thumb": {"clip": "7244292", "t": 7.5, "line1": "손으로 불던 거", "line2": "이제 132홀로"},
  "watermarks": {"ad": "[광고]", "shop": "nanatem_shop"}
}
"""
import subprocess, os, re, sys, json, difflib, copy, uuid, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------------------------------------------------------------- machine-specific paths
# Every path below is THIS PC's. A different machine overrides them with a sibling
# `local_paths.json` (see local_paths.example.json) instead of editing this file.
_DEFAULTS = {
    "tts_dir": r"C:\Users\IdeaPad\Desktop\숏파인더 채널\_script",  # holds elevenlabs_tts.py + .env (ElevenLabs API key)
    "capcut_root": r"C:\Users\IdeaPad\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft",
    "caption_font": r"C:\Users\IdeaPad\AppData\Local\CapCut\User Data\Cache\effect\7480847118538706181\892de34daab569720c6dbc43537e8cf5\font.ttf",  # 서울한강체 B
    "thumb_font_id": "7528305055972199681",  # 카페24 단정해 (CapCut cloud font resource id)
    "thumb_font": r"C:\Users\IdeaPad\AppData\Local\CapCut\User Data\Cache\effect\7528305055972199681\0e4893968fe2d82714917f69c69826aa\font.ttf",
    "template_draft": "nail_ad_v3",  # any draft already saved by THIS machine's CapCut; source of the shadow/font JSON shape
    "voice_id": "5I7B1di44aCL15NkP0jn",  # Kanna
}
_local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_paths.json")
_cfg = {**_DEFAULTS, **(json.load(open(_local_path, encoding="utf-8")) if os.path.exists(_local_path) else {})}
for _k in ("caption_font", "thumb_font"):
    if not os.path.exists(_cfg[_k]):
        sys.exit(f"{_k} not found: {_cfg[_k]}\n"
                  f"On a new machine: open CapCut, apply that font to any text once (so it's cached), "
                  f"then set the real path in {_local_path} (copy local_paths.example.json).")

TTS_DIR = _cfg["tts_dir"]
ROOT = _cfg["capcut_root"]
FONT = _cfg["caption_font"]
CAFE24_ID = _cfg["thumb_font_id"]
CAFE24 = _cfg["thumb_font"]
TEMPLATE_DRAFT = _cfg["template_draft"]
DEFAULT_VOICE_ID = _cfg["voice_id"]
W, H, FPS, F = 1080, 1920, 30, 33333  # F = one frame in microseconds
MAX_SCENE_S = 3.05  # user rule: every clip <= 3 s and a single shot (no cut inside)
# watermark look the user finalized in CapCut: no background, not bold, semi-transparent text
WM_AD = {"size": 6, "scale": 1.105, "x": 0.794, "y": 0.915, "alpha": 0.46}           # [광고] top-right
WM_SHOP = {"size": 14.97, "scale": 0.74, "x": 0.0, "y": -0.44, "alpha": 0.22}         # nanatem_shop horizontally centred, lower-middle
# thumbnail title placement/size the user finalized (CapCut units)
TH1 = {"size": 27, "scale": 0.805, "y": 0.559}
TH2 = {"size": 25, "scale": 0.853, "y": 0.409}


def run(*a):
    subprocess.run(a, check=True)


def dur(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).decode())


def find_clip(cfg, key):
    hits = [f for f in os.listdir(cfg["src_dir"]) if f.lower().endswith(".mp4") and key in f]
    if len(hits) != 1:
        sys.exit(f"clip key {key!r} matched {hits}")
    return os.path.join(cfg["src_dir"], hits[0])


def probe(path):
    o = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                                 "-of", "json", path]).decode("utf-8", "replace")
    j = json.loads(o)
    return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])


_CUTS = {}


def shot_cuts(path):
    """times (s) where the source itself cuts to a different shot (ffmpeg scene detection, cached per file)."""
    if path not in _CUTS:
        out = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-vf", "select='gt(scene,0.25)',showinfo", "-an", "-f", "null", "-"],
                             capture_output=True).stderr.decode("utf-8", "replace")
        _CUTS[path] = [round(float(x), 3) for x in re.findall(r"pts_time:([0-9.]+)", out)]
    return _CUTS[path]


def snap_starts(cfg):
    """a scene that starts just BEFORE a source cut would open with frames of the previous shot (the bug behind the 'no other shot
    in a clip' rule). If a cut lies within 0.35 s after the requested start, move the start onto that cut."""
    for i, s in enumerate(cfg["scenes"], 1):
        for c in shot_cuts(find_clip(cfg, s["clip"])):
            if s["start"] < c <= s["start"] + 0.35:
                print(f"scene {i}: start {s['start']:.2f} -> {c + 0.017:.3f} (snapped to the source cut at {c:.2f})")
                s["start"] = c + 0.017  # half a frame after the cut so the last frame of the old shot is never included


def list_shots(cfg):
    """`shots` command: print each source clip's cut times so scenes can be chosen inside a single shot."""
    for f in sorted(os.listdir(cfg["src_dir"])):
        if f.lower().endswith(".mp4") and "완성본" not in f:  # skip the user's own finished renders
            p = os.path.join(cfg["src_dir"], f)
            w, h, d = probe(p)
            cuts = shot_cuts(p)
            edges = [0.0] + cuts + [round(d, 2)]
            print(f"{f}  {w}x{h}  {d:.1f}s\n   shots: " + ", ".join(f"{a:.2f}-{b:.2f}" for a, b in zip(edges, edges[1:])))


def check_scenes(cfg, per):
    """rule: every scene <= 3 s and entirely inside one shot of its source clip. Aborts with the shot list otherwise."""
    bad = []
    for i, (s, n) in enumerate(zip(cfg["scenes"], per), 1):
        a, b = s["start"], s["start"] + n / FPS
        if n / FPS > MAX_SCENE_S:
            bad.append(f"scene {i}: {n / FPS:.2f}s is longer than {MAX_SCENE_S}s - split the beat into several scenes")
        cuts = [c for c in shot_cuts(find_clip(cfg, s["clip"])) if a - 0.02 < c < b + 0.02]
        if cuts and not s.get("allow_cut"):
            bad.append(f"scene {i}: {a:.2f}-{b:.2f}s of {s['clip']} crosses a cut at {cuts} - move start or shorten (run `shots`)")
    if bad:
        sys.exit("SCENE RULE VIOLATIONS:\n  " + "\n  ".join(bad))


def capcut_fit(w, h, crop=(0, 1), cx=0.5):
    """CapCut clip scale / transform that reproduces the cover-fit crop on the ORIGINAL clip (so it stays trimmable).
    CapCut first fits the clip inside the canvas; scale is relative to that. transform is in half-canvas units (+x right, +y up)."""
    y0, y1 = crop
    f = min(W / w, H / h)
    p = max(W / w, H / (h * (y1 - y0)))
    return p / f, (0.5 - cx) * w * p / (W / 2), ((y0 + y1) / 2 - 0.5) * h * p / (H / 2)


# ---------------------------------------------------------------- voice
def voice(cfg):
    sys.path.insert(0, TTS_DIR)
    import elevenlabs_tts as t
    wd = cfg["workdir"]
    os.makedirs(wd, exist_ok=True)
    raw = os.path.join(wd, "raw.mp3")
    kw = {"voice_id": cfg.get("voice_id", DEFAULT_VOICE_ID)}
    t.generate_narration(cfg["script"], raw, **kw)  # includes silence removal -> no gaps
    run("ffmpeg", "-v", "error", "-y", "-i", raw, "-af", f"atempo={cfg.get('post_tempo', 1.06)}", os.path.join(wd, "narration.mp3"))
    from faster_whisper import WhisperModel
    m = WhisperModel("medium", device="cpu", compute_type="int8")  # cached in ~/.cache/huggingface
    segs, _ = m.transcribe(os.path.join(wd, "narration.mp3"), language="ko", word_timestamps=True)
    words = [(x.word.strip(), round(float(x.start), 3), round(float(x.end), 3)) for s in segs for x in s.words]
    json.dump(words, open(os.path.join(wd, "words.json"), "w", encoding="utf-8"), ensure_ascii=False)
    caps = make_caps(cfg, words, dur(os.path.join(wd, "narration.mp3")))
    with open(os.path.join(wd, "caps.txt"), "w", encoding="utf-8") as f:  # Read this file to choose cut points
        f.write("\n".join(f"{i} {a:.2f}-{b:.2f} {tx}" for i, (a, b, tx) in enumerate(caps)))
    print("narration", round(dur(os.path.join(wd, "narration.mp3")), 2), "s; caption preview -> caps.txt")
    # pronunciation check: whisper heard something different from the script = Kanna probably mispronounced it (e.g. onomatopoeia like 스르륵)
    heard = "".join(c for w, _, _ in words for c in w if re.match(r"\w", c))
    want = "".join(c for c in cfg["script"] if re.match(r"\w", c))
    sm = difflib.SequenceMatcher(None, want, heard, autojunk=False)
    sus = [(want[i1 - 3:i2 + 3], heard[j1 - 3:j2 + 3]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
    if sus:
        print("PRONUNCIATION CHECK - script vs heard (ask the user to listen; rewrite or cut these words):")
        for a, b in sus:
            print(f"   script '{a}'  heard '{b}'")


def make_caps(cfg, words, adur):
    """align script characters to whisper word times; 2-word bursts that never cross a sentence end."""
    wc, wt = [], []
    for w, a, b in words:
        cs = [c for c in w if re.match(r"\w", c)]
        for k, c in enumerate(cs):
            wc.append(c)
            wt.append(a + (b - a) * k / max(1, len(cs)))
    toks = cfg["script"].split()
    sc, tokidx = [], []
    for i, tk in enumerate(toks):
        for c in "".join(c for c in tk if re.match(r"\w", c)):
            sc.append(c)
            tokidx.append(i)
    tm = [None] * len(sc)
    for blk in difflib.SequenceMatcher(None, "".join(wc), "".join(sc), autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            tm[blk.b + k] = wt[blk.a + k]
    n = len(tm)
    for i in range(n):
        if tm[i] is None:
            j = i
            while j < n and tm[j] is None:
                j += 1
            a = tm[i - 1] if i > 0 else 0.0
            b = tm[j] if j < n else adur
            for k in range(i, j):
                tm[k] = a + (b - a) * (k - i + 1) / (j - i + 1)
    tokstart = {}
    for c, ti in zip(tm, tokidx):
        tokstart.setdefault(ti, c)
    groups, cur = [], []
    for i, tk in enumerate(toks):
        cur.append(i)
        if len(cur) == 2 or re.search(r"[.?~!]$", tk):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    chunks = [(" ".join(re.sub(r"[.,~?!]", "", toks[i]) for i in g), tokstart[g[0]]) for g in groups]
    end = round(adur * FPS) / FPS + 1 / FPS
    return [((a if k else 0.0), (chunks[k + 1][1] if k + 1 < len(chunks) else end), t) for k, (t, a) in enumerate(chunks)]  # contiguous


# ---------------------------------------------------------------- text rendering
def fit(lines, path, maxw, cap=200):
    s = cap
    while s > 40:
        f = ImageFont.truetype(path, s)
        if max(f.getlength(t) for t in lines) <= maxw:
            return f, s
        s -= 2


def shadowed(layers, size, dx, dy, blur, stroke=0):
    """black 100% shadow toward lower-right (-45deg), gaussian blurred; optional thin black stroke."""
    sh = Image.new("L", size, 0)
    d = ImageDraw.Draw(sh)
    for xy, t, f, _ in layers:
        d.text((xy[0] + dx, xy[1] + dy), t, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
    sh = sh.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: min(255, int(v * 1.6)))
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    img.paste((0, 0, 0, 255), mask=sh)
    d = ImageDraw.Draw(img)
    for xy, t, f, fill in layers:
        d.text(xy, t, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    return img


def wm_text(text, px, cap_x, cap_y, alpha, path):
    """watermark: plain semi-transparent white text, no background, not bold. cap_x/cap_y = CapCut transform (+y up)."""
    f = ImageFont.truetype(FONT, px)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((W / 2 + cap_x * W / 2, H / 2 - cap_y * H / 2), text, font=f, fill=(255, 255, 255, int(255 * alpha)), anchor="mm")
    im.save(path)


def fit_args(s):
    """ffmpeg filter args that turn a source clip into 1080x1920.
    crop:[y0,y1]  keep only rows y0..y1 (removes foreign subtitles / watermarks / UI).
    fit:"blur"    keep the cropped band at full width and fill the rest with a blurred copy
                  (use when the product sits where a cover-fit crop would cut it off)."""
    y0, y1 = s.get("crop", [0, 1])
    cr = f"crop=iw:ih*{y1 - y0}:0:ih*{y0}"
    if s.get("fit") == "blur":
        fc = (f"[0:v]{cr},split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40[bg];"
              f"[b]scale={W}:-2:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS}[v]")
        return ["-filter_complex", fc, "-map", "[v]"]
    cx = s.get("cx", 0.5)  # horizontal centre (0..1) of the window kept after the cover-fit zoom
    return ["-vf", f"{cr},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}:(iw-{W})*{cx}:0,setsar=1,fps={FPS}"]


# ---------------------------------------------------------------- build
def build(cfg):
    wd = cfg["workdir"]
    P = lambda n: os.path.join(wd, n)
    AUD = P("narration.mp3")
    adur = dur(AUD)
    NF = round(adur * FPS) + 1
    words = json.load(open(P("words.json"), encoding="utf-8"))
    caps = make_caps(cfg, words, adur)
    json.dump(caps, open(P("caps.json"), "w", encoding="utf-8"), ensure_ascii=False)

    # scenes: cut points follow the narration
    sc = cfg["scenes"]
    cuts = []
    for s in sc[:-1]:
        c = s["cut_at"]
        if isinstance(c, str):
            hit = [a for a, b, t in caps if c in t]
            if not hit:
                sys.exit(f"cut_at text {c!r} not found in captions")
            c = hit[0]
        cuts.append(round(c * FPS))
    per = [b - a for a, b in zip([0] + cuts, cuts + [NF])]
    if min(per) < 20:
        print("WARNING: a scene is shorter than 20 frames", per)
    snap_starts(cfg)  # start on the source cut instead of a few frames before it
    check_scenes(cfg, per)  # <= 3 s and no cut inside a scene
    for i, (s, n) in enumerate(zip(sc, per), 1):
        run("ffmpeg", "-v", "error", "-y", "-ss", str(s["start"]), "-i", find_clip(cfg, s["clip"]), "-frames:v", str(n), "-an",
            *fit_args(s), "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", P(f"scene{i}.mp4"))
    NS = len(sc)

    # thumbnail
    th = cfg["thumb"]
    run("ffmpeg", "-v", "error", "-y", "-ss", str(th["t"]), "-i", find_clip(cfg, th["clip"]), "-frames:v", "1",
        *fit_args(th), P("thumb_base.png"))  # th may carry the same crop/fit options as a scene
    L1, L2 = th["line1"], th["line2"]
    f, s = fit([L1, L2], CAFE24, int(W * 0.86), cap=136)  # 카페24 단정해; two lines sit 7.5% of the height apart like the user's layout
    lay = []
    for t, cap_y, c in [(L1, TH1["y"], (255, 255, 255, 255)), (L2, TH2["y"], (0xbb, 0xff, 0xb4, 255))]:
        bb = f.getbbox(t)
        lay.append(((int((W - f.getlength(t)) / 2), int(H / 2 - cap_y * H / 2 - (bb[1] + bb[3]) / 2)), t, f, c))
    ov = shadowed(lay, (W, H), int(s * 0.06), int(s * 0.06), s * 0.075)
    Image.alpha_composite(Image.open(P("thumb_base.png")).convert("RGBA"), ov).convert("RGB").save(P("thumbnail.jpg"), quality=95)

    # captions + watermarks
    cf, csz = fit([c[2] for c in caps], FONT, W - 90, cap=100)
    cf = ImageFont.truetype(FONT, csz)
    for i, (a, b, t) in enumerate(caps, 1):
        shadowed([((int((W - cf.getlength(t)) / 2), int(H / 2 - csz * 0.6)), t, cf, (255, 255, 255, 255))], (W, H),
                 int(csz * 0.07), int(csz * 0.07), csz * 0.09, 3).save(P(f"cap{i:02d}.png"))
    wm = cfg.get("watermarks", {"ad": "[광고]", "shop": "nanatem_shop"})
    wm_text(wm["ad"], 36, WM_AD["x"], WM_AD["y"], WM_AD["alpha"], P("wm_ad.png"))
    wm_text(wm["shop"], 58, WM_SHOP["x"], WM_SHOP["y"], WM_SHOP["alpha"], P("wm_shop.png"))

    # render mp4: thumbnail = first frame, everything else shifted by 1 frame
    DUR = NF / FPS
    args = ["ffmpeg", "-v", "error", "-y"]
    for i in range(1, NS + 1):
        args += ["-i", P(f"scene{i}.mp4")]
    imgs = [f"cap{i:02d}.png" for i in range(1, len(caps) + 1)] + ["wm_ad.png", "wm_shop.png"]
    for im in imgs:
        args += ["-loop", "1", "-framerate", "30", "-t", "40", "-i", P(im)]
    ai = NS + len(imgs)
    ti = ai + 1
    args += ["-i", AUD, "-i", P("thumbnail.jpg")]
    fg = "".join(f"[{i}:v]" for i in range(NS)) + f"concat=n={NS}:v=1:a=0[b0];"
    last = "b0"
    for k, im in enumerate(imgs):
        a, b = (caps[k][0], caps[k][1]) if k < len(caps) else (0, DUR)
        fg += f"[{last}][{NS + k}:v]overlay=enable='between(t,{a:.3f},{b:.3f})':format=auto:shortest=1[o{k}];"
        last = f"o{k}"
    fg += (f"[{last}]format=yuv420p,setsar=1[m];[{ti}:v]scale={W}:{H},format=yuv420p,setsar=1,fps=30,trim=end_frame=1,setpts=PTS-STARTPTS[t];"
           f"[t][m]concat=n=2:v=1:a=0[v];[{ai}:a]adelay=33.333|33.333,apad,atrim=0:{DUR + 1 / 30:.4f}[a]")
    args += ["-filter_complex", fg, "-map", "[v]", "-map", "[a]", "-r", "30", "-c:v", "libx264", "-crf", "17", "-preset", "medium",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", P("shorts.mp4")]
    run(*args)

    make_draft(cfg, caps, per, L1, L2, NS)
    print("scenes(frames)", per, "| mp4:", P("shorts.mp4"))


def make_draft(cfg, caps, per, L1, L2, NS):
    import pycapcut as cc
    from pycapcut import TrackType, Timerange, ClipSettings
    wd, NAME = cfg["workdir"], cfg["name"]
    P = lambda n: os.path.join(wd, n)
    folder = cc.DraftFolder(ROOT)
    if os.path.exists(os.path.join(ROOT, NAME)):
        try:
            folder.remove(NAME)
        except PermissionError:
            sys.exit(f"{NAME} is open in CapCut. Close it (or use a new name) and rerun.")
    s_ = folder.create_draft(NAME, W, H, FPS, allow_replace=True)
    for nm, tp in (("main", TrackType.video), ("nar", TrackType.audio), ("thumb1", TrackType.text), ("thumb2", TrackType.text),
                   ("caps", TrackType.text), ("wm", TrackType.text), ("wm2", TrackType.text)):
        s_.add_track(tp, nm)
    s_.add_segment(cc.VideoSegment(P("thumb_base.png"), Timerange(0, F)), "main")
    # ORIGINAL clips (ASCII copies in workdir/src) so the user can trim/extend each scene in CapCut up to the full source length.
    # CapCut scale/position reproduces the crop; originals are muted. Scenes with "erase": true keep the full frame
    # (the user removes the foreign subtitles with CapCut's AI 제거, which cannot be scripted).
    os.makedirs(P("src"), exist_ok=True)
    staged, t, need_erase = {}, F, []
    for i, (s, nn) in enumerate(zip(cfg["scenes"], per), 1):
        d = round(nn * 1e6 / FPS)
        if s["clip"] not in staged:
            dst = P(f"src/clip{len(staged) + 1}.mp4")
            shutil.copy(find_clip(cfg, s["clip"]), dst)
            staged[s["clip"]] = (dst,) + probe(dst)[:2]
        dst, w, h = staged[s["clip"]]
        crop = (0, 1) if s.get("erase") else tuple(s.get("crop", (0, 1)))
        sc_, tx, ty = capcut_fit(w, h, crop, s.get("cx", 0.5))
        if s.get("erase"):
            need_erase.append(f"scene {i}: {os.path.basename(dst)} {s['start']:.2f}-{s['start'] + nn / FPS:.2f}s (timeline {t / 1e6:.2f}s)")
        s_.add_segment(cc.VideoSegment(dst, Timerange(t, d), source_timerange=Timerange(round(s["start"] * 1e6), d), volume=0.0,
                                       clip_settings=ClipSettings(scale_x=sc_, scale_y=sc_, transform_x=tx, transform_y=ty)), "main")
        t += d
    if need_erase:
        print("CAPCUT AI 제거 needed on:\n   " + "\n   ".join(need_erase))
    s_.add_segment(cc.AudioSegment(P("narration.mp3"), Timerange(F, cc.AudioMaterial(P("narration.mp3")).duration)), "nar")
    total = t
    for tr, txt, col, cfg_ in (("thumb1", L1, (1, 1, 1), TH1), ("thumb2", L2, (0xbb / 255, 1, 0xb4 / 255), TH2)):
        s_.add_segment(cc.TextSegment(txt, Timerange(0, F), style=cc.TextStyle(size=cfg_["size"], color=col, align=1),
                                      clip_settings=ClipSettings(scale_x=cfg_["scale"], scale_y=cfg_["scale"], transform_y=cfg_["y"])), tr)
    sty = cc.TextStyle(size=12, color=(1, 1, 1), align=1)
    for a, b, txt in caps:
        st, en = F + round(a * 1e6), F + round(b * 1e6)
        s_.add_segment(cc.TextSegment(txt, Timerange(st, en - st), style=sty, border=cc.TextBorder(alpha=1.0, color=(0, 0, 0), width=8)), "caps")
    wm = cfg.get("watermarks", {"ad": "[광고]", "shop": "nanatem_shop"})
    def pl(txt, g):  # watermark: no background, not bold, semi-transparent text
        return cc.TextSegment(txt, Timerange(F, total - F), style=cc.TextStyle(size=g["size"], bold=False, color=(1, 1, 1), alpha=g["alpha"], align=1),
                              clip_settings=ClipSettings(scale_x=g["scale"], scale_y=g["scale"], transform_x=g["x"], transform_y=g["y"]))
    s_.add_segment(pl(wm["ad"], WM_AD), "wm")
    s_.add_segment(pl(wm["shop"], WM_SHOP), "wm2")
    s_.save()
    # pycapcut has no shadow API: patch shadow + fonts into the caption/thumbnail text materials
    dp = os.path.join(ROOT, NAME, "draft_content.json")
    d = json.load(open(dp, encoding="utf8"))
    tmpl = json.load(open(os.path.join(ROOT, TEMPLATE_DRAFT, "draft_content.json"), encoding="utf8"))["materials"]["texts"][0]
    wmids = {seg["material_id"] for tr in d["tracks"][-2:] for seg in tr["segments"]}
    for m in d["materials"]["texts"]:
        if m["id"] in wmids:
            continue
        c = json.loads(m["content"])
        isth = c["text"] in (L1, L2)
        FP = CAFE24.replace("\\", "/") if isth else tmpl["font_path"]  # thumbnail = 카페24 단정해, captions = 서울한강체 B
        m.update(has_shadow=True, shadow_color="#000000", shadow_alpha=1.0, shadow_smoothing=0.15, shadow_distance=5.0, shadow_angle=-45.0,
                 shadow_point={"x": 0.6363961030678928, "y": -0.6363961030678928}, font_path=FP, font_name="", check_flag=m.get("check_flag", 7) | 32)
        if isth:
            m.update(font_resource_id=CAFE24_ID, font_source_platform=1,
                     fonts=[{"id": str(uuid.uuid4()).upper(), "resource_id": CAFE24_ID, "third_resource_id": "", "category_id": "", "category_name": "",
                             "source_platform": 1, "path": FP, "effect_id": CAFE24_ID, "title": "카페24 단정해", "team_id": "", "file_uri": "",
                             "request_id": ""}])
        else:
            m.update(font_resource_id=tmpl["font_resource_id"], font_source_platform=1, fonts=copy.deepcopy(tmpl["fonts"]))
            m["fonts"][0]["id"] = str(uuid.uuid4()).upper()
        st = c["styles"][0]
        st["font"] = {"path": FP, "id": CAFE24_ID} if isth else {"path": tmpl["font_path"], "id": tmpl["font_resource_id"]}
        st["strokes"] = [] if isth else [{"content": {"render_type": "solid", "solid": {"color": [0, 0, 0], "alpha": 1.0}}, "width": 0.016, "mode": 0}]
        st["shadows"] = [{"thickness_projection_angle": -45, "thickness_projection_enable": False, "diffuse": 0.03, "alpha": 1.0, "distance": 5.0,
                          "content": {"render_type": "solid", "solid": {"color": [0, 0, 0]}}, "angle": -45, "thickness_projection_distance": 0}]
        m["content"] = json.dumps(c, ensure_ascii=False)
    json.dump(d, open(dp, "w", encoding="utf8"), ensure_ascii=False)
    shutil.copy(P("thumbnail.jpg"), os.path.join(ROOT, NAME, "draft_cover.jpg"))


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("voice", "build", "shots"):
        sys.exit(__doc__)
    cfg = json.load(open(sys.argv[2], encoding="utf-8"))
    {"voice": voice, "build": build, "shots": list_shots}[sys.argv[1]](cfg)
