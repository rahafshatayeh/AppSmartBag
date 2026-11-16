"""
Follow Me — الكاميرا والبث بعملية (process) والذكاء الاصطناعي بعملية ثانية مستقلة.
هيك البث ما بتأثر أبداً بثقل YOLO / CLIP.
+ التحكم بالماتورات عبر الأردوينو (USB Serial).
"""
import glob
import json
import math
import multiprocessing as mp
import os
import queue
import threading
import time
import traceback
from collections import deque
from multiprocessing import shared_memory

import cv2
import numpy as np
import serial
from flask import Flask, Response, jsonify, request

# ===================== إعدادات =====================
# --- التعرّف ---
SIM_THRESHOLD = 0.72      # حدّ قبول الشخص لما يكون في أكثر من شخص بالصورة
HOLD_BONUS = 0.04         # أسهل بهالمقدار لما نكون ماسكين المستخدم أصلاً
MARGIN = 0.04             # لازم المستخدم يتفوق على ثاني أعلى شخص بهالفرق
UPDATE_SIM = 0.80         # تحديث تلقائي لصور المستخدم (بيتأقلم مع الإضاءة والزاوية)
SINGLE_THRESHOLD = 0.60   # إذا في شخص واحد بس بالصورة ولسا كنا ماسكينه قبل شوي: بنقبله بحد أسهل
SINGLE_RECENT_S = 6.0     # "قبل شوي" = آخر هالعدد من الثواني
W_CLIP, W_HIST = 0.7, 0.3
REID_INTERVAL = 2.5       # كل قديش نتأكد بـ CLIP (الثقيل) إنه نفس الشخص. بين التأكيدات تتبع سريع بـ YOLO بس
LOST_AFTER = 1.5

# --- الكاميرا / الأداء ---
STREAM_W = 640
STREAM_QUALITY = 60
STREAM_FPS = 12           # فريمات البث للصفحة بالثانية (أقل = معالج أكثر للذكاء الاصطناعي)
YOLO_IMGSZ = 320
YOLO_CONF = 0.35
KP_CONF = 0.5
TORCH_THREADS = 4         # عملية الذكاء الاصطناعي لحالها (البث بعملية ثانية)

# --- المسافة ---
CAMERA_HFOV_DEG = None    # None = تلقائي من موديل الكاميرا (والأفضل تعملي معايرة)
PERSON_REAL_HEIGHT_M = 1.70
CAMERA_HEIGHT_M = None    # ارتفاع الكاميرا عن الأرض (اختياري)
CAMERA_TILT_DEG = 0.0
CALIB_FILE = "calib.json"

FRAC_NOSE, FRAC_SHOULDER, FRAC_HIP, FRAC_KNEE, FRAC_ANKLE = 0.91, 0.818, 0.530, 0.285, 0.039

# --- التسجيل (4 صور) ---
REGISTER_STEPS = [   # (رسالة عربي, عدد الصور, رسالة للفيديو)
    ("قفي وجهك للكاميرا (من الأمام)", 1, "FACE THE CAMERA (FRONT)"),
    ("دوري ظهرك للكاميرا (من الخلف)", 1, "BACK TO CAMERA"),
    ("خلّي جنبك الأيمن للكاميرا (يمين)", 1, "RIGHT SIDE TO CAMERA"),
    ("خلّي جنبك الأيسر للكاميرا (يسار)", 1, "LEFT SIDE TO CAMERA"),
]
PAUSE_SECONDS = 3.0
CAPTURE_GAP = 0.3

# --- التحقق من وضعية التسجيل ---
REG_POSE_NAMES = ["front", "back", "right", "left"]   # نفس ترتيب REGISTER_STEPS
POSE_KP_CONF = 0.35          # أقل ثقة لاعتبار المفصل ظاهر
SIDE_RATIO_MAX = 0.45        # عرض الأكتاف / طول الجذع: أقل منها = جانبية
FRONTBACK_RATIO_MIN = 0.60   # أكبر منها = أمام أو خلف
FACE_CONF = 0.5              # ثقة الوجه لاعتباره ظاهر
POSE_STABLE_FRAMES = 2       # لازم الوضعية تكون صح لإطارين ورا بعض قبل التصوير

METHOD_AR = {"pose": "مفاصل", "box": "صندوق", "ground": "أرضية", "box_trunc": "جزء من الجسم"}

# --- الحركة (الماتورات) ---
TARGET_DIST_M = 1.0      # مسافة الأمان
DIST_DEADBAND = 0.15     # بتبلش تمشي لما تصير المسافة أكبر من 1.15 م
DRIVE_PWR = 255          # قوة المشي المستقيم: العجلتين نفس القوة الكاملة
TURN_DIR = 1             # إذا الشنطة بتلف عكس جهة الشخص خليها -1
TURN_ENTER_DEG = 12.0    # الشخص أبعد من هيك عن النص -> وقوف ولف بالمكان باتجاهه
TURN_EXIT_DEG = 6.0      # بنوقف اللف لما يرجع الشخص للنص (هامش الخطأ)
PIVOT_PWR = 165          # قوة اللف (مثبتة من التجارب)
PULSE_MIN_S = 0.10       # أقصر نبضة لف (ثانية) — للزوايا الصغيرة
PULSE_PER_DEG = 0.006    # قديش تطول النبضة لكل درجة زيادة
PULSE_MAX_S = 0.10       # أطول نبضة لف (ثانية) (مثبتة من التجارب)
PIVOT_CONFIRM_S = 0.20   # لازم الشخص يضل بعيد عن النص هالمدة (ثانية) قبل ما نلف (بيشيل القفزات)
PULSE_SETTLE_S = 0.12    # بعد نبضة اللف: وقفة قصيرة لتثبت الصورة (مع التتبع السريع)
FAST_TRACK = True        # تتبع سريع بكل فريم (optical flow) بين نتائج الذكاء الاصطناعي
FAST_FRESH_S = 0.25      # الزاوية السريعة بتنستخدم إذا عمرها أقل من هيك
PIVOT_NOW_DEG = 25.0     # إلا إذا الزاوية كبيرة كثير -> لف فوراً
ANG_SMOOTH = 0.5         # تنعيم الزاوية (0 = بدون، 0.8 = ناعم كثير وأبطأ)
SEARCH_PULSES = 3        # إذا الشخص طلع من طرف الصورة: كم نبضة بتلف باتجاهه (0 = بدون بحث)
SEARCH_PWR = 255         # قوة اللف وقت البحث
STEER_DEADBAND = 6.0     # وهي ماشية: إذا الشخص انزاح أكثر من هيك، بتلف شوي وهي ماشية
STEER_INNER = 190        # قوة العجلة الداخلية وقت اللف وهي ماشية (الخارجية بتضل 255)
                         # أقل رقم = لف أقوى. ما تنزليها تحت 170 وإلا العجلة بتوقف على الأرض
SEND_HZ = 20
INFO_STALE = 2.0         # إذا معلومات الكاميرا أقدم من هيك نوقف
SERIAL_BAUD = 57600         # لازم نفس Serial.begin بكود الأردوينو
# --- توازن العجلات (بتتعدّل من الصفحة وبتنحفظ) ---
LEFT_PWR_START = 255     # قوة اليسار بالمشي المستقيم (مثبتة من التجارب)
RIGHT_PWR_START = 255    # قوة اليمين بالمشي المستقيم (الوزن صار متساوي)
BAL_MIN = 150            # أقل قيمة مسموحة (تحتها العجلة بتوقف على الأرض)

# ---- السرعة حسب المسافة ----
#  بعيد (أكثر من FAST_DIST_M) = أقصى سرعة. قريب (أقل من SLOW_DIST_M) = سرعة بطيئة.
#  بالنص بينهم: السرعة بتنزل تدريجياً. وعند مسافة الأمان (1 م) بتوقف.
SPEED_BY_DIST = True
SLOW_PWR = 200           # قوة المشي البطيء لما تكون قريبة (لازم تضل كافية تحرّك الشنطة على الأرض)
SLOW_DIST_M = 1.4        # أقل من هيك = بطيء
FAST_DIST_M = 2.0        # أكثر من هيك = أقصى سرعة (255 للعجلتين)
SPEED_CFG_VER = 2        # إذا تغيّر، إعدادات السرعة القديمة المحفوظة بتنتجاهل
DIST_SMOOTH = 0.6        # تنعيم المسافة عشان السرعة ما تقفز (0 = بدون)
BALANCE_FILE = "balance.json"

# ---- الميزان (HX711 على الـ Mega: DT -> 4, SCK -> 5) ----
# الأردوينو هو اللي بيحسب الغرامات وبيعمل التصفير والمعايرة (محفوظة بالـ EEPROM).
# الرازبيري بس بيقرأ: W,غرامات,ثابت,معايَر  وبيبعتله أوامر: z (تصفير) و K,غرامات (معايرة)
WEIGHT_FILE = "weight.json"   # وزن الشنطة فاضية + الحد المسموح
WEIGHT_LIMIT_DEFAULT = 23.0   # حد وزن الشنطة (كغم) — حد المطار العادي
W_TIMEOUT_S = 2.0        # إذا ما وصل إشي من الميزان هالمدة = مش موصول
W_MOVE_HOLD_S = 1.5      # بعد ما توقف الماتورات بنستنى هالمدة قبل ما نعتبر القراءة دقيقة
TEST_SEC = 2.0           # مدة زر "جرّبي مستقيم"
TEST_TURN_SEC = 1.0      # مدة زر "جرّبي لف" (لف متواصل)


def make_info(status, **kw):
    d = {"status": status, "kind": "idle", "sim": 0, "dir": "-", "dist": "-", "dist_m": None,
         "angle": None, "lateral_m": None, "stop": True}
    d.update(kw)
    return d


# =====================================================================
#                    عملية الذكاء الاصطناعي (AI process)
# =====================================================================
torch = open_clip = Image = None
yolo = clip_model = preprocess = CLAHE = None


def _ai_init():
    global torch, open_clip, Image, yolo, clip_model, preprocess, CLAHE
    import torch as _torch
    import open_clip as _oc
    from PIL import Image as _Image
    from ultralytics import YOLO

    torch, open_clip, Image = _torch, _oc, _Image
    torch.set_num_threads(TORCH_THREADS)
    cv2.setNumThreads(1)
    print("[AI] جاري تحميل النماذج...", flush=True)
    if os.path.isdir("yolov8n-pose_ncnn_model"):
        yolo = YOLO("yolov8n-pose_ncnn_model", task="pose")
    else:
        yolo = YOLO("yolov8n-pose.pt")
    clip_model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="laion2b_s34b_b79k")
    clip_model.eval()
    CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    print("[AI] جاهز!", flush=True)


def clahe_bgr(img):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = CLAHE.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def body_parts(frame, box, kp=None):
    """القميص (الجذع) والبنطلون. إذا المفاصل ظاهرة بنقص بالزبط من الأكتاف للحوض،
    هيك القص بيضل صح حتى لو الشخص قريب وراسه أو رجليه طالعين من الصورة."""
    x1, y1, x2, y2 = box
    h, w = y2 - y1, x2 - x1
    if kp is not None:
        K = 0.4
        sh = [kp[i] for i in (5, 6) if kp[i][2] >= K]
        hp = [kp[i] for i in (11, 12) if kp[i][2] >= K]
        if sh and hp:
            sy = min(float(p[1]) for p in sh)
            hy = max(float(p[1]) for p in hp)
            th = hy - sy
            if th > 25:
                xs = [float(p[0]) for p in sh + hp]
                mx = max(0.15 * th, 6)
                tx1, tx2 = int(max(x1, min(xs) - mx)), int(min(x2, max(xs) + mx))
                ty1, ty2 = int(max(y1, sy + 0.05 * th)), int(min(y2, hy + 0.05 * th))
                torso = frame[ty1:ty2, tx1:tx2]
                legs = frame[int(min(y2 - 2, hy)):y2, tx1:tx2]
                if torso.shape[0] > 10 and torso.shape[1] > 10:
                    if legs.shape[0] < 10:
                        legs = torso
                    return torso, legs
    torso = frame[y1 + int(.12 * h): y1 + int(.62 * h), x1 + int(.10 * w): x2 - int(.10 * w)]
    legs = frame[y1 + int(.55 * h): y2, x1 + int(.15 * w): x2 - int(.15 * w)]
    return torso, legs


def color_hist(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4],
                        [0, 180, 0, 256, 0, 256]).flatten().astype(np.float32)
    return hist / (hist.sum() + 1e-6)


def extract(frame, boxes, kps=None):
    imgs, hists = [], []
    for i, box in enumerate(boxes):
        torso, legs = body_parts(frame, box, kps[i] if kps is not None else None)
        rgb = cv2.cvtColor(clahe_bgr(torso), cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (224, 224))
        imgs.append(preprocess(Image.fromarray(rgb)))
        hists.append((color_hist(torso), color_hist(legs)))
    with torch.inference_mode():
        f = clip_model.encode_image(torch.stack(imgs))
        f = f / f.norm(dim=-1, keepdim=True)
    return f, hists


def hist_sim(a, b):
    return 1.0 - cv2.compareHist(a, b, cv2.HISTCMP_BHATTACHARYYA)


def score_all(frame, boxes, ref, kps=None):
    feats, hists = extract(frame, boxes, kps)
    with torch.inference_mode():
        gal = torch.stack(ref["feats"])
        scores = []
        for i in range(len(boxes)):
            sims = gal @ feats[i]
            clip_s = float(sims.topk(min(2, len(sims))).values.mean())
            ht, hl = hists[i]
            hs = max(0.65 * hist_sim(ht, gt) + 0.35 * hist_sim(hl, gl) for gt, gl in ref["hists"])
            scores.append(W_CLIP * clip_s + W_HIST * hs)
    return scores, feats, hists


def detect_people(frame, conf=YOLO_CONF):
    """(صناديق, مفاصل) — المفاصل مصفوفة (17,3) لكل شخص: x,y,ثقة."""
    res = yolo.predict(frame, imgsz=YOLO_IMGSZ, conf=conf, verbose=False)[0]
    xyxy = res.boxes.xyxy.tolist()
    kp_all = None
    if res.keypoints is not None and len(xyxy):
        try:
            kp_all = res.keypoints.data.cpu().numpy()
        except Exception:
            kp_all = None
    boxes, kpts = [], []
    for i, b in enumerate(xyxy):
        x1, y1, x2, y2 = map(int, b)
        x1, y1 = max(x1, 0), max(y1, 0)
        if x2 - x1 > 30 and y2 - y1 > 60:
            boxes.append((x1, y1, x2, y2))
            kpts.append(kp_all[i] if kp_all is not None and i < len(kp_all) else None)
    return boxes, kpts


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def shift_box(b, dx, dy):
    return (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)


# ---------- المسافة من مفاصل الجسم ----------
def body_points(kp, w, h):
    def ok(i):
        return kp[i][2] >= KP_CONF and 3 < kp[i][1] < h - 3 and 3 < kp[i][0] < w - 3

    def mid_y(i, j):
        ys = [kp[k][1] for k in (i, j) if ok(k)]
        return sum(ys) / len(ys) if ys else None

    pts = []
    if ok(0):
        pts.append((float(kp[0][1]), FRAC_NOSE))
    for ids, frac in (((5, 6), FRAC_SHOULDER), ((11, 12), FRAC_HIP),
                      ((13, 14), FRAC_KNEE), ((15, 16), FRAC_ANKLE)):
        y = mid_y(*ids)
        if y is not None:
            pts.append((float(y), frac))
    return pts


def pose_scale(pts):
    """عدد البكسلات اللي بيساويها الطول الكامل للشخص (انحدار خطي على المفاصل الظاهرة)."""
    if len(pts) < 2:
        return None
    y = np.array([p[0] for p in pts])
    fr = np.array([p[1] for p in pts])
    if fr.max() - fr.min() < 0.25:
        return None
    fm, ym = fr.mean(), y.mean()
    s = -float(((fr - fm) * (y - ym)).sum() / ((fr - fm) ** 2).sum())
    return s if s > 20 else None


def measure_scale(box, kp, w, h):
    if kp is not None:
        s = pose_scale(body_points(kp, w, h))
        if s:
            return s, "pose"
    x1, y1, x2, y2 = box
    truncated = y1 <= 3 or y2 >= h - 3
    return float(y2 - y1), ("box_trunc" if truncated else "box")


def dist_from_scale(s, calib):
    """المسافة من مقياس الجسم s (بكسل للطول الكامل).
    - بدون نقاط معايرة: نموذج العدسة (focal).
    - مع نقاط (يفضّل 3): جدول بيعوّض عن تشوّه العدسة الواسعة (استيفاء بين النقاط)."""
    inv = calib["person_h"] / max(s, 1.0)          # بيتناسب طردياً مع المسافة
    pts = sorted(calib.get("points") or [])
    if not pts:
        return calib["focal_px"] * inv
    if len(pts) == 1 or inv <= pts[0][0]:
        return pts[0][1] * inv / pts[0][0]
    if inv >= pts[-1][0]:
        return pts[-1][1] * inv / pts[-1][0]
    for (i0, z0), (i1, z1) in zip(pts, pts[1:]):
        if i0 <= inv <= i1:
            return z0 + (z1 - z0) * (inv - i0) / (i1 - i0)
    return pts[-1][1]


def estimate_position(box, kp, w, h, calib):
    x1, y1, x2, y2 = box
    f = calib["focal_px"]
    cx = (x1 + x2) / 2
    if kp is not None:                     # مركز الجذع (أكتاف + حوض) أثبت بكثير من مركز الصندوق
        xs = [float(kp[i][0]) for i in (5, 6, 11, 12) if kp[i][2] >= 0.4]
        if len(xs) >= 2:
            cx = sum(xs) / len(xs)
    angle = math.degrees(math.atan((cx - w / 2) / f))
    s, method = measure_scale(box, kp, w, h)
    dist = dist_from_scale(s, calib)
    if CAMERA_HEIGHT_M and y2 < h - 3:
        ang = math.atan((y2 - h / 2) / f) + math.radians(CAMERA_TILT_DEG)
        if ang > 0.02:
            dist, method = CAMERA_HEIGHT_M / math.tan(ang), "ground"
    return {"dist": dist, "angle": angle, "method": method, "scale": s,
            "reliable": method != "box_trunc", "cx": cx}


# ---------- التحقق من وضعية التسجيل ----------
def check_reg_pose(kp, box, step):
    """بترجّع (صح؟, رسالة عربي, رسالة انجليزي للفيديو)."""
    want = REG_POSE_NAMES[step]
    K = POSE_KP_CONF
    if kp is None:
        return False, "ما شفت مفاصلك، قفي كاملة قدام الكاميرا", "STAND FULLY IN VIEW"
    c = lambda i: float(kp[i][2])

    # عرض الأكتاف
    if c(5) >= K and c(6) >= K:
        sh_w = abs(kp[5][0] - kp[6][0])
        sh_mid_x = (kp[5][0] + kp[6][0]) / 2
        sh_mid_y = (kp[5][1] + kp[6][1]) / 2
    elif max(c(5), c(6)) >= K:                # كتف وحد ظاهر (غالباً جانبية)
        i = 5 if c(5) >= c(6) else 6
        sh_w, sh_mid_x, sh_mid_y = 0.0, float(kp[i][0]), float(kp[i][1])
    else:
        return False, "ما شفت أكتافك، قفي كاملة قدام الكاميرا", "SHOULDERS NOT VISIBLE"

    # طول الجذع (أكتاف -> حوض)
    hips = [kp[i] for i in (11, 12) if c(i) >= K]
    if hips:
        hx = sum(float(p[0]) for p in hips) / len(hips)
        hy = sum(float(p[1]) for p in hips) / len(hips)
        torso = math.hypot(hx - sh_mid_x, hy - sh_mid_y)
    else:
        torso = (box[3] - box[1]) * (FRAC_SHOULDER - FRAC_HIP)
    torso = max(torso, 1.0)
    ratio = sh_w / torso

    # ---------- أمام / خلف ----------
    if want in ("front", "back"):
        if ratio < FRONTBACK_RATIO_MIN:
            if want == "front":
                return False, "عدّلي وضعيتك: لفي وجهك وكتافك للكاميرا بشكل مستقيم", "TURN FACE TO CAMERA (STRAIGHT)"
            return False, "عدّلي وضعيتك: لفي ظهرك وكتافك للكاميرا بشكل مستقيم", "TURN BACK TO CAMERA (STRAIGHT)"
        face = max(c(0), (c(1) + c(2)) / 2)
        left_on_image_right = kp[5][0] > kp[6][0]       # الكتف الأيسر ع يمين الصورة = وجه للكاميرا
        if want == "front":
            if face < FACE_CONF or not left_on_image_right:
                return False, "عدّلي وضعيتك: وجهك لازم يكون للكاميرا (مش ظهرك)", "FACE MUST BE TOWARD CAMERA"
        else:
            if face >= FACE_CONF or left_on_image_right:
                return False, "عدّلي وضعيتك: دوري ظهرك للكاميرا (لسا شايف وجهك)", "TURN YOUR BACK TO CAMERA"
        return True, "", ""

    # ---------- يمين / يسار ----------
    name_ar = "الأيمن" if want == "right" else "الأيسر"
    if ratio > SIDE_RATIO_MAX:
        return False, f"عدّلي وضعيتك: لفي جنبك {name_ar} للكاميرا بشكل كامل", f"TURN FULLY: {want.upper()} SIDE TO CAMERA"

    vote = None
    if c(0) >= K:                                           # اتجاه الأنف مقارنة بالأكتاف
        off = (float(kp[0][0]) - sh_mid_x) / torso
        if abs(off) > 0.06:
            vote = "right" if off > 0 else "left"           # أنف ع يمين الصورة = جنبك الأيمن للكاميرا
    if vote is None:                                        # احتياط: أي أذن ظاهرة
        de = c(4) - c(3)
        if abs(de) > 0.15:
            vote = "right" if de > 0 else "left"
    if vote is None:
        return False, f"عدّلي وضعيتك: ما قدرت أحدد جنبك، خلّي جنبك {name_ar} للكاميرا", f"SHOW YOUR {want.upper()} SIDE"
    if vote != want:
        return False, f"الجنب غلط! بدي جنبك {name_ar} للكاميرا", f"WRONG SIDE - NEED {want.upper()} SIDE"
    return True, "", ""


# ---------- التسجيل ----------
def send_thumb(S, frame, box, idx):
    """بتبعت صورة الشخص الملتقطة (مقصوصة) لصفحة الويب."""
    try:
        x1, y1, x2, y2 = box
        h, w = frame.shape[:2]
        mx, my = int((x2 - x1) * 0.08), int((y2 - y1) * 0.05)
        crop = frame[max(y1 - my, 0):min(y2 + my, h), max(x1 - mx, 0):min(x2 + mx, w)]
        ok, jpg = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            S["res_q"].put({"thumb": idx, "jpeg": jpg.tobytes(), "ack": S["ack"]}, timeout=1.0)
    except Exception:
        pass


def do_registration(S, frame, boxes, w, kp_of):
    cx = w / 2
    box = min(boxes, key=lambda b: abs((b[0] + b[2]) / 2 - cx))

    # ---- تحقق من الوضعية قبل أي تصوير ----
    ok, hint_ar, hint_en = check_reg_pose(kp_of.get(box), box, S["reg_step"])
    if not ok:
        S["pose_ok"] = 0
        S["reg_hint"], S["reg_hint_ar"] = hint_en, hint_ar
        return box, hint_ar, False
    S["pose_ok"] += 1
    if S["pose_ok"] < POSE_STABLE_FRAMES:                # نتأكد إنها ثابتة مش صدفة
        S["reg_hint"], S["reg_hint_ar"] = "", ""
        return box, f"{S['reg_msg']} — خليكي ثابتة...", False
    S["pose_ok"] = 0
    S["reg_hint"], S["reg_hint_ar"] = "", ""

    send_thumb(S, frame, box, S["reg_step"])
    feats, hists = extract(frame, [box], [kp_of.get(box)])
    S["samples"].append((feats[0], hists[0]))
    S["reg_left"] -= 1
    S["reg_done"] += 1
    S["shots"] += 1
    S["reg_warn"] = False
    S["flash"] = True
    if S["reg_left"] <= 0:
        S["reg_step"] += 1
        if S["reg_step"] >= len(REGISTER_STEPS):
            s = S["samples"]
            S["ref"] = {"feats": [x[0] for x in s], "hists": [x[1] for x in s], "n_base": len(s)}
            S["samples"] = []
            S["reg_step"] = -1
            S["reg_en"] = ""
            S["reg_msg"] = "تم التسجيل ✅"
            return box, "تم التسجيل ✅", True
        msg, cnt, en = REGISTER_STEPS[S["reg_step"]]
        S.update(reg_left=cnt, reg_msg=msg, reg_en=en, reg_pause_until=time.time() + PAUSE_SECONDS)
        return box, msg, True
    return box, f"{S['reg_msg']} ({S['reg_done']}/{S['reg_total']})", True


def handle_cmds(cmd_q, S):
    while True:
        try:
            c = cmd_q.get_nowait()
        except queue.Empty:
            return
        kind, cid = c[0], c[-1]
        S["ack"] = cid
        if kind == "register":
            msg, cnt, en = REGISTER_STEPS[0]
            S.update(ref=None, samples=[], reg_step=0, reg_left=cnt, reg_msg=msg, reg_en=en,
                     reg_warn=False, shots=0, reg_done=0,
                     reg_total=sum(x[1] for x in REGISTER_STEPS),
                     reg_pause_until=time.time() + PAUSE_SECONDS,
                     pose_ok=0, reg_hint="", reg_hint_ar="")
        elif kind == "reset":
            S.update(ref=None, samples=[], reg_step=-1, reg_left=0, reg_warn=False,
                     pose_ok=0, reg_hint="", reg_hint_ar="")
        elif kind == "set_calib":
            S["calib"] = dict(c[1])


def read_frame(bufs, seq, last):
    s1 = seq.value
    if s1 == last:
        return None, last
    f = bufs[s1 % 2].copy()
    if seq.value - s1 >= 2:          # انكتب فوقه أثناء النسخ -> نعيد المحاولة
        return None, last
    return f, s1


def _ai_loop(bufs, seq, cmd_q, res_q, S):
    last = -1
    ref_id = -1
    tr = {}
    scales, dists = deque(maxlen=5), deque(maxlen=5)
    angs = deque(maxlen=3)

    def reset_tracker():
        tr.update(box=None, last_verify=0.0, last_ok=time.time(), sim=0.0,
                  last_update=0.0, lost=False, vel=(0.0, 0.0), t=time.time())
        scales.clear()
        dists.clear()
        angs.clear()
        tr["ang_s"] = None

    def meas_of(method):
        if not scales:
            return None
        return {"s": float(np.median(scales)), "method": method, "t": time.time()}

    def pub(info, overlay=None, kp_draw=None, meas=None):
        msg = {"ack": S["ack"], "info": info, "overlay": overlay or [], "kp_draw": kp_draw or [],
               "reg": {"active": S["reg_step"] >= 0, "pause_until": S["reg_pause_until"],
                       "en": S["reg_en"], "msg": S["reg_msg"], "warn": S["reg_warn"],
                       "done": S["reg_done"], "total": S["reg_total"], "shots": S["shots"],
                       "hint": S["reg_hint"], "hint_ar": S["reg_hint_ar"],
                       "registered": S["ref"] is not None},
               "diag": dict(S["diag"])}
        if meas is not None:
            msg["meas"] = meas
        try:
            res_q.put_nowait(msg)
        except queue.Full:
            pass

    reset_tracker()
    while True:
        handle_cmds(cmd_q, S)
        frame, s_new = read_frame(bufs, seq, last)
        if frame is None:
            time.sleep(0.004)
            continue
        last = s_new
        now = time.time()
        step, ref = S["reg_step"], S["ref"]

        if id(ref) != ref_id:
            ref_id = id(ref)
            reset_tracker()

        # ---- فترة الاستعداد ----
        if step >= 0 and now < S["reg_pause_until"]:
            S["reg_warn"] = False
            S["reg_hint"], S["reg_hint_ar"], S["pose_ok"] = "", "", 0
            pub(make_info(S["reg_msg"], kind="register"))
            time.sleep(0.05)
            continue

        h, w = frame.shape[:2]
        t0 = time.time()
        boxes, kpts = detect_people(frame, conf=0.2 if step >= 0 else YOLO_CONF)
        kp_of = dict(zip(boxes, kpts))
        S["diag"]["people"] = len(boxes)
        S["diag"]["det_ms"] = int((time.time() - t0) * 1000)

        # ---- تسجيل ----
        if step >= 0:
            if not boxes:
                S["reg_warn"] = True
                S["reg_hint"], S["reg_hint_ar"], S["pose_ok"] = "", "", 0
                pub(make_info("ما شفتك! قفي كاملة قدام الكاميرا", kind="warn"))
                continue
            box, status, captured = do_registration(S, frame, boxes, w, kp_of)
            color = (0, 0, 255) if S["reg_hint"] else (255, 200, 0)
            pub(make_info(status, kind="register"), overlay=[(box, color, "Registering")])
            if captured:
                time.sleep(CAPTURE_GAP)
            continue

        # ---- قبل التسجيل (معايرة المسافة ممكنة هون) ----
        if ref is None:
            kp_draw, meas = [], None
            if boxes:
                tgt = min(boxes, key=lambda b: abs((b[0] + b[2]) / 2 - w / 2))
                s, m = measure_scale(tgt, kp_of.get(tgt), w, h)
                if m != "box_trunc":
                    scales.append(s)
                    meas = meas_of(m)
                if kp_of.get(tgt) is not None:
                    kp_draw = [(int(x), int(y)) for x, y, c in kp_of[tgt] if c >= KP_CONF]
            pub(make_info("غير مسجّل" if boxes else "ما في أشخاص بالصورة"),
                overlay=[(b, (200, 200, 200), "") for b in boxes], kp_draw=kp_draw, meas=meas)
            continue

        # ---- تتبع ----
        pred = None
        if tr["box"] is not None and not tr["lost"]:
            dt = min(now - tr["t"], 1.0)
            pred = shift_box(tr["box"], tr["vel"][0] * dt, tr["vel"][1] * dt)

        user_box = None
        scores_by_box = {}
        if boxes:
            if pred is not None:
                cand = max(boxes, key=lambda b: iou(b, pred))
                if iou(cand, pred) >= 0.25:
                    crowded = any(b != cand and iou(b, cand) > 0.05 for b in boxes)
                    if not crowded and now - tr["last_verify"] < REID_INTERVAL:
                        user_box = cand

            if user_box is None:
                scores, feats, hists = score_all(frame, boxes, ref, [kp_of.get(b) for b in boxes])
                scores_by_box = dict(zip(boxes, scores))
                order = sorted(range(len(boxes)), key=lambda i: -scores[i])
                bi = order[0]
                best_s = scores[bi]
                second = scores[order[1]] if len(order) > 1 else 0.0
                tr["sim"] = best_s
                thr = SIM_THRESHOLD - HOLD_BONUS if pred is not None else SIM_THRESHOLD
                if len(boxes) == 1 and now - tr["last_ok"] < SINGLE_RECENT_S:
                    thr = min(thr, SINGLE_THRESHOLD)   # شخص واحد بس وكنا ماسكينه قبل شوي -> أسهل
                if best_s >= thr and (len(order) == 1 or best_s - second >= MARGIN):
                    user_box = boxes[bi]
                    tr["last_verify"] = now
                    if len(boxes) == 1 and best_s >= UPDATE_SIM and now - tr["last_update"] > 2.0:
                        ref["feats"].append(feats[bi])
                        ref["hists"].append(hists[bi])
                        if len(ref["feats"]) > ref["n_base"] + 8:
                            ref["feats"].pop(ref["n_base"])
                            ref["hists"].pop(ref["n_base"])
                        tr["last_update"] = now

        overlay, kp_draw, meas = [], [], None
        if user_box is not None:
            if tr["box"] is not None:
                dt = max(now - tr["t"], 1e-3)
                if dt < 1.0:
                    ob, nb = tr["box"], user_box
                    nv = (((nb[0] + nb[2]) - (ob[0] + ob[2])) / 2 / dt,
                          ((nb[1] + nb[3]) - (ob[1] + ob[3])) / 2 / dt)
                    tr["vel"] = (0.5 * tr["vel"][0] + 0.5 * nv[0], 0.5 * tr["vel"][1] + 0.5 * nv[1])
            else:
                tr["vel"] = (0.0, 0.0)
            tr.update(box=user_box, last_ok=now, lost=False, t=now)

            kp = kp_of.get(user_box)
            pos = estimate_position(user_box, kp, w, h, S["calib"])
            if pos["reliable"]:
                dists.append(pos["dist"])
                scales.append(pos["scale"])
                meas = meas_of(pos["method"])
            d = float(np.median(dists)) if dists else pos["dist"]
            angs.append(pos["angle"])
            ang_med = float(np.median(angs))
            tr["ang_s"] = ang_med if tr.get("ang_s") is None else ANG_SMOOTH * tr["ang_s"] + (1 - ANG_SMOOTH) * ang_med
            ang = tr["ang_s"]
            direction = "يسار" if ang < -5 else ("يمين" if ang > 5 else "منتصف")
            lateral = d * math.tan(math.radians(ang))
            prefix = "" if pos["reliable"] else "≤ "
            info = make_info(
                "تم التعرف عليكِ", kind="tracking", sim=round(tr["sim"] * 100), dir=direction,
                dist=f"{prefix}{d:.2f} م", dist_m=round(d, 2), angle=round(ang, 1),
                lateral_m=round(lateral, 2), stop=False,
                method=pos["method"], method_ar=METHOD_AR[pos["method"]],
                reliable=bool(pos["reliable"]),
                box=[int(v) for v in user_box], cx=float(pos["cx"]), seq=int(last),
                ang_off=float(ang - pos["angle"]))
            for b in boxes:
                if b == user_box:
                    overlay.append((b, (0, 255, 0), f"{tr['sim']*100:.0f}% {prefix}{d:.1f}m"))
                else:
                    s_ = scores_by_box.get(b)
                    overlay.append((b, (0, 0, 255), f"{s_*100:.0f}%" if s_ else ""))
            if kp is not None:
                kp_draw = [(int(x), int(y)) for x, y, c in kp if c >= KP_CONF]
        else:
            if now - tr["last_ok"] > LOST_AFTER:
                tr["lost"] = True
                tr["box"] = None
                dists.clear()
                scales.clear()
                angs.clear()
                tr["ang_s"] = None
                status, kind = "فقدت المستخدم — الروبوت متوقف", "lost"
            else:
                status, kind = "أبحث عنك...", "search"
            note = ("ما في أشخاص بالصورة" if not boxes
                    else "في أشخاص بالصورة بس ما قدرت أتعرف عليكِ بينهم")
            info = make_info(status, kind=kind, note=note, sim=round(tr["sim"] * 100))
            for b in boxes:
                s_ = scores_by_box.get(b)
                overlay.append((b, (0, 0, 255), f"{s_*100:.0f}%" if s_ else ""))

        pub(info, overlay=overlay, kp_draw=kp_draw, meas=meas)


def ai_main(shm_name, shape, seq, cmd_q, res_q, calib_init):
    """نقطة دخول عملية الذكاء الاصطناعي."""
    _ai_init()
    shm = shared_memory.SharedMemory(name=shm_name)
    bufs = np.ndarray((2,) + tuple(shape), dtype=np.uint8, buffer=shm.buf)
    S = dict(calib=dict(calib_init), ack=0, ref=None, samples=[], reg_step=-1, reg_left=0,
             reg_msg="", reg_en="", reg_warn=False, reg_pause_until=0.0, reg_total=0,
             reg_done=0, shots=0, flash=False, diag={"people": 0, "det_ms": 0, "err": ""},
             pose_ok=0, reg_hint="", reg_hint_ar="")
    S["res_q"] = res_q
    res_q.put({"ready": True})
    while True:
        try:
            _ai_loop(bufs, seq, cmd_q, res_q, S)
        except Exception:
            err = traceback.format_exc()
            print(err, flush=True)
            S["diag"]["err"] = err.strip().splitlines()[-1][:120]
            try:
                res_q.put_nowait({"ack": 0, "diag": dict(S["diag"]), "only_diag": True})
            except queue.Full:
                pass
            time.sleep(1.0)


# =====================================================================
#                 عملية الكاميرا + الويب (main process)
# =====================================================================
app = Flask(__name__)
lock = threading.Lock()
cond = threading.Condition()
shared = {"jpeg": None, "jid": 0}
G = {}   # cmd_q, res_q, proc

REG_IDLE = {"active": False, "pause_until": 0.0, "en": "", "msg": "", "warn": False,
            "done": 0, "total": 0, "shots": 0, "hint": "", "hint_ar": "", "registered": False}
state = {
    "ready": False,
    "overlay": [], "kp_draw": [],
    "info": make_info("جاري تحميل النماذج... (ممكن تاخد دقيقة)"),
    "info_t": 0.0,
    "fast": {"box": None, "ang": None, "t": 0.0},   # التتبع السريع بكل فريم
    "reg": dict(REG_IDLE),
    "meas": None,
    "diag": {"people": 0, "det_ms": 0, "err": ""},
    "cmd_id": 0,
    "last_shots": 0,
    "flash_until": 0.0,
    "thumbs": {}, "thumb_ver": 0,
    "calib": {"focal_px": 400.0, "person_h": PERSON_REAL_HEIGHT_M, "points": [], "calibrated": False},
}

MOTOR = {"enabled": False, "connected": False, "port": "", "err": "", "l": 0, "r": 0,
         "why": "", "moving": False, "mode": "idle", "last_ang": 0.0,
         "pulse_end": 0.0, "pulse_side": 1, "pulse_pwr": 0, "pulse_why": "", "search_left": 0,
         "over_since": 0.0,
         "l_pwr": LEFT_PWR_START, "r_pwr": RIGHT_PWR_START, "test_until": 0.0,
         "test_kind": "straight", "test_side": 1,
         "p_pwr": PIVOT_PWR, "p_mode": "pivot", "p_max": PULSE_MAX_S,
         "s_on": SPEED_BY_DIST, "s_pwr": SLOW_PWR, "s_near": SLOW_DIST_M, "s_far": FAST_DIST_M,
         "d_s": None, "spd": 0}


def focal_from_fov(width_px, hfov_deg):
    return (width_px / 2) / math.tan(math.radians(hfov_deg) / 2)


def save_calib():
    c = state["calib"]
    json.dump({**c, "points": [list(p) for p in c["points"]], "out_w": G["out_w"], "v": 3},
              open(CALIB_FILE, "w"))


def send_cmd(*args):
    with lock:
        state["cmd_id"] += 1
        cid = state["cmd_id"]
    G["cmd_q"].put((*args, cid))


def result_loop():
    while True:
        try:
            r = G["res_q"].get(timeout=1.0)
        except queue.Empty:
            if G["proc"] is not None and not G["proc"].is_alive():
                with lock:
                    state["diag"]["err"] = "عملية الذكاء الاصطناعي توقفت! شوفي التيرمينال"
            continue
        with lock:
            if r.get("ready"):
                state["ready"] = True
                state["info"] = make_info("غير مسجّل")
                continue
            if "thumb" in r:
                if r.get("ack", 0) >= state["cmd_id"]:
                    state["thumbs"][r["thumb"]] = r["jpeg"]
                    state["thumb_ver"] += 1
                continue
            state["diag"].update(r.get("diag", {}))
            if r.get("only_diag") or r.get("ack", 0) < state["cmd_id"]:
                continue                      # نتيجة قديمة قبل آخر أمر
            state["overlay"] = r["overlay"]
            state["kp_draw"] = r["kp_draw"]
            state["info"] = r["info"]
            state["info_t"] = time.time()
            state["reg"] = r["reg"]
            if r.get("meas") is not None:
                state["meas"] = r["meas"]
            if r["reg"]["shots"] > state["last_shots"]:
                state["flash_until"] = time.time() + 0.25
            state["last_shots"] = r["reg"]["shots"]


class FastTracker:
    """تتبع سريع جداً بكل فريم كاميرا (Lucas-Kanade optical flow) على نقاط من جسم الشخص.
    الذكاء الاصطناعي بطيء وبيرجع نتيجة لصورة قديمة؛ هون بناخد نتيجته وبنقدّمها
    للفريم الحالي (fast-forward) وبعدين بنتبع الشخص فريم بفريم لحد النتيجة الجاية.
    هيك المربع الأخضر والزاوية ما بيتأخروا عن الشخص."""
    SCALE = 2                                   # بنشتغل على صورة نص الحجم (أسرع)

    def __init__(self):
        self.ring = deque(maxlen=60)            # (seq, gray) آخر ثانيتين تقريباً
        self.box = None                         # بإحداثيات الصورة الكاملة
        self.cx = None
        self.pts = None
        self.gray = None
        self.ver = -1
        self.lk = dict(winSize=(15, 15), maxLevel=2,
                       criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, 0.03))

    def _feats(self, gray, box):
        k = self.SCALE
        x1, y1, x2, y2 = [int(v / k) for v in box]
        w, h = x2 - x1, y2 - y1
        if w < 6 or h < 6:
            return None
        mask = np.zeros_like(gray)              # الجذع بس (مش الخلفية ولا الإيدين)
        mask[y1 + int(.15 * h):y1 + int(.65 * h), x1 + int(.2 * w):x2 - int(.2 * w)] = 255
        return cv2.goodFeaturesToTrack(gray, maxCorners=40, qualityLevel=0.01, minDistance=4, mask=mask)

    def _flow(self, g0, g1, pts):
        if pts is None or len(pts) < 4:
            return None, 0.0, 0.0
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(g0, g1, pts, None, **self.lk)
        if nxt is None:
            return None, 0.0, 0.0
        good = st.reshape(-1) == 1
        if good.sum() < 4:
            return None, 0.0, 0.0
        d = (nxt[good] - pts[good]).reshape(-1, 2)
        return nxt[good].reshape(-1, 1, 2), float(np.median(d[:, 0])), float(np.median(d[:, 1]))

    def _shift(self, dx, dy):
        k = self.SCALE
        x1, y1, x2, y2 = self.box
        self.box = (x1 + dx * k, y1 + dy * k, x2 + dx * k, y2 + dy * k)
        self.cx += dx * k

    def step(self, seq_id, frame, ai):
        """ai = آخر نتيجة تتبع من الذكاء الاصطناعي (أو None إذا ما في شخص)."""
        k = self.SCALE
        g = cv2.cvtColor(cv2.resize(frame, (frame.shape[1] // k, frame.shape[0] // k)), cv2.COLOR_BGR2GRAY)
        self.ring.append((seq_id, g))
        if ai is None:
            self.box = self.pts = None
            self.gray = g
            return
        if ai["ver"] != self.ver:               # نتيجة جديدة: نقدّمها من فريمها للفريم الحالي
            self.ver = ai["ver"]
            frames = [fg for sq, fg in self.ring if sq >= ai["seq"]]
            self.box, self.cx = tuple(float(v) for v in ai["box"]), float(ai["cx"])
            if len(frames) >= 2:
                pts = self._feats(frames[0], self.box)
                for g0, g1 in zip(frames, frames[1:]):
                    pts, dx, dy = self._flow(g0, g1, pts)
                    if pts is None:
                        break
                    self._shift(dx, dy)
            self.pts = self._feats(g, self.box)
            self.gray = g
            return
        if self.box is not None and self.gray is not None:      # بين النتائج: فريم بفريم
            pts, dx, dy = self._flow(self.gray, g, self.pts)
            if pts is not None:
                self._shift(dx, dy)
                self.pts = pts if len(pts) >= 8 else self._feats(g, self.box)
            else:
                self.pts = self._feats(g, self.box)
        self.gray = g


def capture_loop(picam2, bufs, seq):
    last_enc = 0.0
    ft = FastTracker()
    ai_ver = 0
    last_info = None
    while True:
        frame = picam2.capture_array()
        bufs[(seq.value + 1) % 2][:] = frame      # للذكاء الاصطناعي (shared memory)
        seq.value += 1
        now_c = time.time()

        # ---- التتبع السريع بكل فريم ----
        if FAST_TRACK:
            with lock:
                info_now = state["info"]
                focal = state["calib"]["focal_px"]
            if info_now is not last_info:
                last_info = info_now
                ai_ver += 1
            ai = None
            if info_now.get("kind") == "tracking" and info_now.get("box") is not None:
                ai = {"ver": ai_ver, "seq": info_now.get("seq", 0), "box": info_now["box"],
                      "cx": info_now.get("cx", (info_now["box"][0] + info_now["box"][2]) / 2)}
            try:
                ft.step(seq.value, frame, ai)
            except Exception as e:
                ft.box = None
                print("[FAST]", e, flush=True)
            fast = {"box": None, "ang": None, "t": now_c}
            if ft.box is not None:
                ang = math.degrees(math.atan((ft.cx - frame.shape[1] / 2) / focal))
                fast = {"box": [int(v) for v in ft.box], "ang": ang + info_now.get("ang_off", 0.0), "t": now_c}
            with lock:
                state["fast"] = fast

        # البث للصفحة بس STREAM_FPS بالثانية (بيوفر معالج للذكاء الاصطناعي)
        if now_c - last_enc < 1.0 / STREAM_FPS:
            continue
        last_enc = now_c

        with lock:
            overlay = list(state["overlay"])
            kp_draw = list(state["kp_draw"])
            fast_box = state["fast"]["box"]
            reg = dict(state["reg"])
            flash = time.time() < state["flash_until"]
            err = state["diag"]["err"]
            ready = state["ready"]

        pause_left = reg["pause_until"] - time.time()
        in_pause = reg["active"] and pause_left > 0
        out = frame.copy()
        for (x1, y1, x2, y2), color, text in overlay:
            if fast_box is not None and tuple(color) == (0, 255, 0):
                dx = fast_box[0] - x1                     # المربع الأخضر من التتبع السريع (بدون تأخير)
                x1, y1, x2, y2 = fast_box
                kp_draw = [(px + dx, py) for px, py in kp_draw]
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            if text:
                cv2.putText(out, text, (x1, max(y1 - 8, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        for (px, py) in kp_draw:
            cv2.circle(out, (px, py), 3, (255, 255, 0), -1)

        W_, H_ = out.shape[1], out.shape[0]
        step_txt = f"STEP {min(reg['done'] + 1, max(reg['total'], 1))}/{reg['total']}: {reg['en']}"
        if not ready:
            cv2.putText(out, "LOADING AI MODELS...", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        if in_pause:
            cv2.rectangle(out, (0, 0), (W_, 70), (0, 140, 255), -1)
            cv2.putText(out, step_txt, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(out, "GET READY - NOT CAPTURING YET", (10, 58),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(out, str(int(math.ceil(pause_left))), (W_ // 2 - 40, H_ // 2 + 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 6, (0, 140, 255), 14)
        elif reg["active"]:
            bad = reg["warn"] or bool(reg.get("hint"))
            cv2.rectangle(out, (0, 0), (W_, 70), (0, 0, 200) if bad else (0, 160, 0), -1)
            cv2.putText(out, step_txt, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            if reg["warn"]:
                line2 = "NO PERSON - NOT CAPTURING"
            elif reg.get("hint"):
                line2 = "ADJUST YOUR POSE - NOT CAPTURING"
            else:
                line2 = "CAPTURING - HOLD STILL"
            cv2.putText(out, line2, (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            if reg["warn"]:
                cv2.rectangle(out, (0, H_ - 45), (W_, H_), (0, 0, 255), -1)
                cv2.putText(out, "NO PERSON DETECTED - STAND IN VIEW", (10, H_ - 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            elif reg.get("hint"):
                cv2.rectangle(out, (0, H_ - 45), (W_, H_), (0, 0, 255), -1)
                cv2.putText(out, reg["hint"][:42], (10, H_ - 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        if err:
            cv2.putText(out, "ERR: " + err[:70], (5, H_ - 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
        if flash:
            out = cv2.addWeighted(out, 0.3, np.full_like(out, 255), 0.7, 0)
            cv2.putText(out, "CAPTURED!", (W_ // 2 - 150, H_ // 2 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 150, 0), 5)

        ok, jpeg = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, STREAM_QUALITY])
        if ok:
            with cond:
                shared["jpeg"] = jpeg.tobytes()
                shared["jid"] += 1
                cond.notify_all()


# ===================== الميزان =====================
WEIGHT = {"g": None, "stable": False, "cal": False, "hx_err": False, "last_t": 0.0,
          "bag_kg": 0.0, "limit": WEIGHT_LIMIT_DEFAULT, "move_t": 0.0, "msg": "", "msg_t": 0.0}
ARD_TX = deque(maxlen=20)        # أوامر للأردوينو من الصفحة/التطبيق (z, K,...)


def save_weight():
    try:
        json.dump({k: WEIGHT[k] for k in ("bag_kg", "limit")}, open(WEIGHT_FILE, "w"))
    except Exception:
        pass


def load_weight():
    try:
        w = json.load(open(WEIGHT_FILE))
        for k in ("bag_kg", "limit"):
            if k in w:
                WEIGHT[k] = float(w[k])
        print(f"[WEIGHT] وزن الشنطة فاضية {WEIGHT['bag_kg']} كغم • الحد {WEIGHT['limit']} كغم", flush=True)
    except Exception:
        pass


def weight_connected():
    return time.time() - WEIGHT["last_t"] < W_TIMEOUT_S


def weight_status():
    """حالة الميزان للتطبيق والصفحة."""
    now = time.time()
    d = {"connected": weight_connected() and not WEIGHT["hx_err"], "kg": None, "items_kg": None,
         "grams": WEIGHT["g"], "stable": False, "moving": now - WEIGHT["move_t"] < W_MOVE_HOLD_S,
         "tared": True, "calibrated": WEIGHT["cal"], "bag_kg": WEIGHT["bag_kg"], "limit": WEIGHT["limit"],
         "err": "", "over": False, "msg": WEIGHT["msg"] if now - WEIGHT["msg_t"] < 6 else ""}
    if not weight_connected():
        d["err"] = "ما في قراءة من الأردوينو (تأكدي إنه كود الميزان مرفوع والـ USB موصول)"
        return d
    if WEIGHT["hx_err"]:
        d["err"] = "الـ HX711 مش موصول (افحصي DT على 4 و SCK على 5 و VCC و GND)"
        return d
    if not WEIGHT["cal"]:
        d["err"] = "الميزان مش معايَر — اعملي المعايرة من الـ Serial Monitor (أمر r)"
    items = max(0.0, (WEIGHT["g"] or 0) / 1000.0)
    d["items_kg"] = round(items, 2)
    d["kg"] = round(items + WEIGHT["bag_kg"], 2)
    d["stable"] = WEIGHT["stable"] and not d["moving"]
    d["over"] = d["kg"] > WEIGHT["limit"]
    return d


def handle_arduino_line(line):
    """سطر من الأردوينو:  W,غرامات,ثابت,معايَر   أو   W,ERR   أو رسائل عادية."""
    if line.startswith("W,"):
        parts = line[2:].split(",")
        with lock:
            WEIGHT["last_t"] = time.time()
            if parts[0] == "ERR":
                WEIGHT["hx_err"] = True
                return
            try:
                WEIGHT["g"] = int(float(parts[0]))
                WEIGHT["stable"] = len(parts) > 1 and parts[1] == "1"
                WEIGHT["cal"] = len(parts) > 2 and parts[2] == "1"
                WEIGHT["hx_err"] = False
            except ValueError:
                pass
    elif line.startswith(("Zero done", "   Zero saved", "   New calibration factor", "   Saved to EEPROM",
                          "ERROR", "No saved")):
        print("[SCALE]", line, flush=True)
        with lock:
            WEIGHT["msg"], WEIGHT["msg_t"] = line.strip(), time.time()


# ===================== التحكم بالماتورات =====================
def pivot_cmd(side, pwr):
    """اللف: side=+1 يمين، -1 يسار.
    pivot: لف بالمكان (عجلة لقدام والثانية لورا) — يمين = اليسار لقدام واليمين لورا.
    swing: عجلة وحدة لقدام والثانية واقفة — يمين = اليسار لقدام بس."""
    s_ = side * TURN_DIR
    p = int(pwr)
    if MOTOR["p_mode"] == "swing":
        return (p, 0) if s_ > 0 else (0, p)
    return (p * s_, -p * s_)


def start_pulse(side, ang_abs, pwr, why):
    """نبضة لف قصيرة، مدتها بتتناسب مع الزاوية. بعدها بنوقف ونستنى صورة جديدة."""
    dur = min(MOTOR["p_max"], PULSE_MIN_S + PULSE_PER_DEG * ang_abs)
    MOTOR.update(pulse_end=time.time() + dur, pulse_side=side, pulse_pwr=pwr, pulse_why=why)
    return pivot_cmd(side, pwr)


def speed_frac(d):
    """قديش من القوة الكاملة: قريب = SLOW، بعيد = 100%، وبالنص تدريجي."""
    M = MOTOR
    if not M["s_on"]:
        return 1.0
    slow = M["s_pwr"] / 255.0
    near, far = M["s_near"], max(M["s_near"] + 0.1, M["s_far"])
    if d <= near:
        return slow
    if d >= far:
        return 1.0
    return slow + (1.0 - slow) * (d - near) / (far - near)


def compute_cmd(info, info_t, det_s):
    """قرار الحركة بطريقة (لف شوي -> وقوف -> شوف -> قرر):
    - الشخص بعيد عن النص (أكثر من TURN_ENTER_DEG): نبضة لف قصيرة باتجاهه، وبعدها
      بنستنى صورة جديدة انلقطت بعد ما وقفنا، وبنقرر من جديد. هيك ما بتتجاوزه أبداً.
    - الشخص رجع للنص (أقل من TURN_EXIT_DEG): مشي مستقيم إذا أبعد من مسافة الأمان.
    - الشخص طلع من طرف الصورة: كم نبضة بس باتجاهه (مش لف 360)."""
    M = MOTOR
    now = time.time()

    # ---- جوا نبضة لف: كمّلها ----
    if now < M["pulse_end"]:
        l, r = pivot_cmd(M["pulse_side"], M["pulse_pwr"])
        return l, r, M["pulse_why"]

    # ---- بعد نبضة لف: استني الصورة تثبت ----
    #  مع التتبع السريع: وقفة قصيرة بس. بدونه: لازم صورة جديدة من الذكاء الاصطناعي.
    if info.get("fast"):
        if now < M["pulse_end"] + PULSE_SETTLE_S:
            return 0, 0, "بستنى الكاميرا تثبت…"
    elif info_t - det_s - 0.10 <= M["pulse_end"]:
        return 0, 0, "بستنى الكاميرا تشوف بعد اللف…"

    tracking = info.get("kind") == "tracking" and info.get("dist_m") is not None

    # ---------- الشخص مش ظاهر ----------
    if not tracking:
        M["moving"] = False
        M["mode"] = "idle"
        M["d_s"] = None
        M["spd"] = 0
        if M["search_left"] > 0 and abs(M["last_ang"]) >= TURN_ENTER_DEG:
            M["search_left"] -= 1
            side = 1 if M["last_ang"] > 0 else -1
            why = "بدوّر عليكِ " + ("يمين ↻" if side > 0 else "يسار ↺")
            l, r = start_pulse(side, 25.0, MOTOR["p_pwr"], why)
            return l, r, why
        return 0, 0, "ما في هدف"

    d = float(info["dist_m"])
    # مسافة ناعمة للسرعة (القراءة بتقفز شوي من فريم لفريم)
    M["d_s"] = d if M["d_s"] is None else M["d_s"] + (d - M["d_s"]) * (1.0 - DIST_SMOOTH)
    ang = float(info.get("angle") or 0.0)
    reliable = info.get("reliable", True)
    M["last_ang"] = ang
    M["search_left"] = SEARCH_PULSES
    side = 1 if ang > 0 else -1
    side_ar = "يمين ↻" if side > 0 else "يسار ↺"

    # ---------- قرار اللف (hysteresis: بنبلش عند 12° وبنوقف عند 6°) ----------
    # ما بنلف على قراءة وحدة: لازم يضل بعيد عن النص PIVOT_CONFIRM_S (إلا لو الزاوية كبيرة كثير)
    if abs(ang) >= TURN_ENTER_DEG:
        if not M["over_since"]:
            M["over_since"] = now
    else:
        M["over_since"] = 0.0
    if M["mode"] == "pivot":
        if abs(ang) <= TURN_EXIT_DEG:
            M["mode"] = "straight"
            M["over_since"] = 0.0
    elif abs(ang) >= PIVOT_NOW_DEG or (M["over_since"] and now - M["over_since"] >= PIVOT_CONFIRM_S):
        M["mode"] = "pivot"
    else:
        M["mode"] = "straight"

    if M["mode"] == "pivot":
        M["moving"] = False
        why = f"بلف {side_ar} ({ang:+.0f}°)"
        l, r = start_pulse(side, abs(ang), MOTOR["p_pwr"], why)
        return l, r, why

    # ---------- الشخص بالنص: مشي مستقيم ----------
    # hysteresis: بتبلش تمشي فوق 1.15م وبتوقف عند 1.0م (عشان ما ترجف)
    if not reliable:
        M["moving"] = False
    elif M["moving"]:
        M["moving"] = d > TARGET_DIST_M
    else:
        M["moving"] = d > TARGET_DIST_M + DIST_DEADBAND

    if not M["moving"]:
        M["spd"] = 0
        return 0, 0, ("قريبة كثير — واقفة" if not reliable else "بالنص ✓ ومسافة الأمان ✓")

    # العجلتين نفس القوة الكاملة. إذا الشخص انزاح شوي، العجلة اللي بجهته بتخف لـ STEER_INNER
    # (بس ما بتنزل لدرجة إنها توقف على الأرض)، وإذا انزاح كثير بيصير لف بالمكان (فوق).
    # السرعة حسب المسافة: بعيد = أسرع إشي، قريب = بطيء
    f = speed_frac(M["d_s"])
    M["spd"] = int(round(f * 100))
    l = max(BAL_MIN, M["l_pwr"] * f)        # قوة كل عجلة من ضبط التوازن بالصفحة × السرعة
    r = max(BAL_MIN, M["r_pwr"] * f)
    k = STEER_INNER / 255.0
    tag = "🚀 أسرع إشي" if f >= 0.99 else ("🐢 بطيء" if f <= M["s_pwr"] / 255.0 + 0.01 else "⏩ متوسط")
    if abs(ang) > STEER_DEADBAND:
        if side * TURN_DIR > 0:
            r = max(BAL_MIN, r * k)
            why = f"{tag} {M['spd']}% • بلف شوي يمين ({d:.2f} م)"
        else:
            l = max(BAL_MIN, l * k)
            why = f"{tag} {M['spd']}% • بلف شوي يسار ({d:.2f} م)"
    else:
        why = f"{tag} {M['spd']}% • مستقيم وراكِ ({d:.2f} م)"
    return int(l), int(r), why


def find_port():
    ports = sorted(glob.glob("/dev/ttyACM*")) + sorted(glob.glob("/dev/ttyUSB*"))
    return ports[0] if ports else None


def save_balance():
    try:
        json.dump(dict({k: MOTOR[k] for k in ("l_pwr", "r_pwr", "p_pwr", "p_mode", "p_max",
                                              "s_on", "s_pwr", "s_near", "s_far")}, s_ver=SPEED_CFG_VER),
                  open(BALANCE_FILE, "w"))
    except Exception:
        pass


def load_balance():
    try:
        b = json.load(open(BALANCE_FILE))
        keys = ["l_pwr", "r_pwr", "p_pwr", "p_max"]
        if b.get("s_ver") == SPEED_CFG_VER:          # إعدادات سرعة من نفس النسخة بس
            keys += ["s_on", "s_pwr", "s_near", "s_far"]
        for k in keys:
            if k in b:
                MOTOR[k] = type(MOTOR[k])(b[k])
        if b.get("p_mode") in ("pivot", "swing"):
            MOTOR["p_mode"] = b["p_mode"]
        print(f"[MOTOR] توازن: يسار {MOTOR['l_pwr']} • يمين {MOTOR['r_pwr']} | "
              f"لف: {MOTOR['p_mode']} قوة {MOTOR['p_pwr']} نبضة {MOTOR['p_max']:.2f}ث | "
              f"سرعة: {'شغّالة' if MOTOR['s_on'] else 'موقفة'} بطيء {MOTOR['s_pwr']} "
              f"({MOTOR['s_near']:.1f}م → {MOTOR['s_far']:.1f}م)", flush=True)
    except Exception:
        pass


def motor_loop():
    load_balance()
    load_weight()
    ser = None
    rx = b""
    while True:
        time.sleep(1.0 / SEND_HZ)
        with lock:
            info = dict(state["info"])
            info_t = state["info_t"]
            det_s = state["diag"].get("det_ms", 0) / 1000.0
            age = time.time() - info_t
            enabled = MOTOR["enabled"]
            fast = dict(state["fast"])
        fast_ok = (FAST_TRACK and info.get("kind") == "tracking" and fast["ang"] is not None
                   and time.time() - fast["t"] < FAST_FRESH_S)
        if fast_ok:
            info["angle"] = fast["ang"]                # زاوية من الفريم الحالي، مش من صورة قديمة
        info["fast"] = fast_ok

        if time.time() < MOTOR["test_until"]:     # أزرار التجربة بالصفحة
            if MOTOR["test_kind"] == "turn":
                l, r = pivot_cmd(MOTOR["test_side"], MOTOR["p_pwr"])
                why = (f"🧪 تجربة لف {'يمين' if MOTOR['test_side'] > 0 else 'يسار'}"
                       f" ({'بالمكان' if MOTOR['p_mode'] == 'pivot' else 'بعجلة وحدة'}) قوة {MOTOR['p_pwr']}")
            else:
                l, r = MOTOR["l_pwr"], MOTOR["r_pwr"]
                why = f"🧪 تجربة مستقيم: يسار {l} • يمين {r}"
            MOTOR.update(moving=False, mode="idle", pulse_end=0.0)
        elif not enabled:
            l, r, why = 0, 0, "الحركة موقفة"
            MOTOR.update(moving=False, mode="idle", pulse_end=0.0, search_left=0)
        elif age > INFO_STALE:
            l, r, why = 0, 0, "ما في معلومات من الكاميرا"
            MOTOR.update(moving=False, mode="idle")
        else:
            l, r, why = compute_cmd(info, info_t, det_s)

        if ser is None:
            port = find_port()
            if port:
                try:
                    ser = serial.Serial(port, SERIAL_BAUD, timeout=0.05, write_timeout=0.1)
                    time.sleep(2.0)                  # الأردوينو بيعمل restart لما ينفتح البورت
                    ser.reset_input_buffer()
                    MOTOR.update(port=port, err="")
                    print(f"[MOTOR] متصل بالأردوينو على {port}", flush=True)
                except Exception as e:
                    ser = None
                    MOTOR["err"] = str(e)[:80]
            else:
                MOTOR["err"] = "ما لقيت الأردوينو (وصليه USB)"

        if ser is not None:
            try:
                ser.write(f"M,{l},{r}\n".encode())
                while ARD_TX:                        # أوامر الميزان من الصفحة/التطبيق
                    ser.write((ARD_TX.popleft() + "\n").encode())
                if ser.in_waiting:                   # رسائل الأردوينو (قراءات الميزان)
                    rx += ser.read(ser.in_waiting)
                    *lines, rx = rx.split(b"\n")
                    for ln in lines:
                        handle_arduino_line(ln.decode(errors="ignore").strip())
                    if len(rx) > 200:
                        rx = b""
            except Exception as e:
                print("[MOTOR] انقطع الاتصال:", e, flush=True)
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                MOTOR["err"] = "انقطع الاتصال بالأردوينو"

        with lock:
            MOTOR.update(l=l, r=r, why=why, connected=ser is not None)
            if l or r:
                WEIGHT["move_t"] = time.time()       # الوزن مش دقيق وهي ماشية


stream_state = {"token": 0}


def generate(token):
    last = -1
    while stream_state["token"] == token:
        with cond:
            cond.wait_for(lambda: shared["jid"] != last, timeout=2.0)
            if shared["jid"] == last:
                continue
            last, data = shared["jid"], shared["jpeg"]
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n")


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Follow Me</title>
<style>
:root{
  --bg:#0b1220; --card:#131c2e; --card2:#1a2540; --line:#26324d;
  --txt:#e8edf7; --mut:#8b9ab8;
  --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --info:#38bdf8; --acc:#6366f1;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);line-height:1.5;
  font-family:"Segoe UI",Tahoma,"Noto Sans Arabic",Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:16px}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px}
h1{font-size:22px;margin:0;display:flex;align-items:center;gap:8px}
h2{font-size:16px;margin:0}
.pill{display:inline-flex;align-items:center;gap:8px;padding:6px 14px;border-radius:999px;
  font-size:13px;font-weight:600;background:var(--card);border:1px solid var(--line)}
.dot{width:10px;height:10px;border-radius:50%;background:var(--mut)}
.pill.ok .dot{background:var(--ok);box-shadow:0 0 8px var(--ok)}
.pill.wait .dot{background:var(--warn)}
.pill.off .dot{background:var(--bad)}
.grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:14px;align-items:start}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.col{display:flex;flex-direction:column;gap:14px;min-width:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px}
.card-h{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;flex-wrap:wrap}

/* الحالة الرئيسية */
.hero{--c:var(--mut);display:flex;align-items:center;gap:14px;padding:14px 16px;border-radius:16px;
  background:var(--card);border:1px solid var(--line);border-inline-start:6px solid var(--c)}
.hero-ic{font-size:34px;width:56px;height:56px;border-radius:14px;background:var(--card2);
  display:flex;align-items:center;justify-content:center;flex:none}
.hero-head{font-size:21px;font-weight:700;color:var(--c)}
.hero-note{font-size:14px;color:var(--mut);margin-top:2px;min-height:21px}
.st-loading{--c:var(--info)} .st-idle{--c:var(--mut)} .st-register{--c:var(--acc)}
.st-warn{--c:var(--warn)} .st-search{--c:var(--warn)}
.st-tracking{--c:var(--ok)} .st-lost{--c:var(--bad)}
.st-loading .hero-ic{animation:spin 1.6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* الفيديو */
.video{position:relative;background:#000;border-radius:12px;overflow:hidden;min-height:200px}
.video img{display:block;width:100%;height:auto}
.live{position:absolute;top:10px;left:10px;background:rgba(239,68,68,.92);color:#fff;
  font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;letter-spacing:1px}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--mut);margin-top:10px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-inline-end:5px;vertical-align:middle}

/* المقاييس */
.metrics{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.tile{background:var(--card2);border-radius:12px;padding:12px;min-width:0}
.tile .lb{font-size:12px;color:var(--mut)}
.tile .vl{font-size:28px;font-weight:700;margin:2px 0;white-space:nowrap}
.tile .vl small{font-size:14px;font-weight:500;color:var(--mut)}
.tile .sb{font-size:12px;color:var(--mut);min-height:18px}
.track{position:relative;height:8px;border-radius:99px;background:var(--line);margin:10px 4px 4px}
.track .tick{position:absolute;left:50%;top:-3px;width:2px;height:14px;background:var(--mut);transform:translateX(-50%)}
.mark{position:absolute;top:50%;left:50%;width:16px;height:16px;border-radius:50%;background:var(--ok);
  transform:translate(-50%,-50%);transition:left .25s;display:none;box-shadow:0 0 8px var(--ok)}
.tl{display:flex;justify-content:space-between;font-size:11px;color:var(--mut)}
.bar{position:relative;height:8px;border-radius:99px;background:var(--line);margin-top:10px;overflow:hidden}
.bar>div{height:100%;width:0;background:var(--ok);transition:width .25s,background .25s}
.bar .thr{position:absolute;top:0;bottom:0;width:2px;background:#fff;opacity:.6}

/* التسجيل */
.badge{font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;background:var(--card2);color:var(--mut)}
.badge.ok{background:rgba(34,197,94,.15);color:var(--ok)}
.badge.warn{background:rgba(245,158,11,.15);color:var(--warn)}
.badge.bad{background:rgba(239,68,68,.15);color:var(--bad)}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}
.step{background:var(--card2);border:1px solid transparent;border-radius:12px;padding:8px 4px;text-align:center;font-size:12px;color:var(--mut)}
.step b{display:flex;margin:0 auto 4px;width:26px;height:26px;border-radius:50%;background:var(--line);
  align-items:center;justify-content:center;font-size:13px;color:var(--txt)}
.step .th{display:none;width:100%;height:96px;object-fit:contain;background:#000;border-radius:8px;margin-bottom:4px;cursor:zoom-in}
.step.has .th{display:block}
.step.has b{display:none}
#lb{position:fixed;inset:0;background:rgba(0,0,0,.88);display:none;align-items:center;justify-content:center;z-index:20;cursor:zoom-out}
#lb img{max-width:92vw;max-height:90vh;border-radius:12px}
.step.cur{border-color:var(--acc);color:var(--txt)}
.step.cur b{background:var(--acc)}
.step.done{color:var(--ok)}
.step.done b{background:var(--ok);color:#06210f}
.instr{display:none;background:var(--card2);border-radius:12px;padding:14px;margin-bottom:12px;text-align:center}
.instr .big{font-size:19px;font-weight:700}
.instr .cd{font-size:56px;font-weight:800;color:var(--warn);line-height:1.1;min-height:62px}
.instr .sm{font-size:13px;color:var(--mut)}
.tips{margin:0 0 12px;padding-inline-start:20px;font-size:13px;color:var(--mut)}
.tips li{margin:2px 0}
.btns{display:flex;gap:8px;flex-wrap:wrap}
button{font-family:inherit;font-size:15px;font-weight:700;border:0;border-radius:12px;padding:10px 18px;
  cursor:pointer;color:#fff;background:var(--acc)}
button:hover:not(:disabled){filter:brightness(1.12)}
button:disabled{opacity:.4;cursor:not-allowed}
button.ghost{background:var(--card2);color:var(--txt);border:1px solid var(--line)}
button.danger{background:var(--bad)}
button.grow{flex:1}
#btn_drive{margin-top:8px;width:100%;padding:8px}

/* المعايرة */
details summary{cursor:pointer;list-style:none;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
details summary::-webkit-details-marker{display:none}
details .body{margin-top:12px;font-size:14px}
.cal-steps{margin:0 0 10px;padding-inline-start:20px;color:var(--mut);font-size:13px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px}
.row label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--mut)}
input{background:var(--card2);border:1px solid var(--line);color:var(--txt);border-radius:10px;
  padding:8px 10px;width:96px;font-size:15px;font-family:inherit}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
.chip{background:var(--card2);border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:12px}
.meas{font-size:13px;padding:8px 10px;border-radius:10px;background:var(--card2);margin-bottom:10px}
.meas.ok{color:var(--ok)} .meas.no{color:var(--warn)}
.msg{font-size:13px;min-height:20px;margin-top:6px}
.msg.ok{color:var(--ok)} .msg.bad{color:var(--bad)}

.alert{display:none;background:rgba(239,68,68,.12);border:1px solid var(--bad);color:#fecaca;
  border-radius:12px;padding:10px 14px;font-size:13px}
.alert code{display:block;direction:ltr;text-align:left;font-size:12px;margin-top:4px;opacity:.9;word-break:break-all}
footer{margin-top:14px;text-align:center;font-size:12px;color:var(--mut)}
#toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%) translateY(30px);opacity:0;
  background:var(--ok);color:#06210f;font-weight:700;padding:12px 22px;border-radius:12px;
  transition:all .3s;pointer-events:none;z-index:9}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>🤖 Follow Me <span style="font-size:13px;font-weight:500;color:var(--mut)">تتبّع المستخدم</span></h1>
  <span id="conn" class="pill wait"><span class="dot"></span><span id="conn_t">جاري الاتصال…</span></span>
</header>

<div id="err" class="alert"><b>⚠️ حصل خطأ بالنظام</b><code id="err_t"></code></div>

<div class="grid" style="margin-top:14px">

  <!-- ========== العمود الأول: الحالة + الفيديو ========== -->
  <div class="col">
    <div id="hero" class="hero st-loading">
      <div id="hero_ic" class="hero-ic">⏳</div>
      <div>
        <div id="hero_head" class="hero-head">جاري التحميل…</div>
        <div id="hero_note" class="hero-note"></div>
      </div>
    </div>

    <div class="card">
      <div class="video">
        <img id="video" src="/video" alt="بث الكاميرا">
        <span class="live">LIVE</span>
      </div>
      <div class="legend">
        <span><i style="background:#00ff00"></i>أنتِ (المستخدم)</span>
        <span><i style="background:#ff0000"></i>أشخاص ثانيين</span>
        <span><i style="background:#c8c8c8"></i>غير مسجّل بعد</span>
        <span><i style="background:#00ffff"></i>نقاط مفاصل الجسم</span>
      </div>
    </div>
  </div>

  <!-- ========== العمود الثاني: القياسات + التسجيل + المعايرة ========== -->
  <div class="col">

    <div class="metrics">
      <div class="tile">
        <div class="lb">📏 المسافة</div>
        <div class="vl"><span id="m_dist">—</span> <small id="m_dist_u" style="display:none">م</small></div>
        <div class="sb" id="m_dist_s">بتظهر لما أتعرف عليكِ</div>
      </div>
      <div class="tile">
        <div class="lb">🧭 الاتجاه</div>
        <div class="vl"><span id="m_dir">—</span> <small id="m_ang"></small></div>
        <div class="track" dir="ltr"><div class="tick"></div><div id="mark" class="mark"></div></div>
        <div class="tl" dir="ltr"><span>يسار</span><span>يمين</span></div>
      </div>
      <div class="tile">
        <div class="lb">🎯 نسبة التشابه</div>
        <div class="vl"><span id="m_sim">—</span><small id="m_sim_u" style="display:none">%</small></div>
        <div class="bar"><div id="sim_bar"></div><span class="thr" style="left:78%"></span></div>
        <div class="sb" style="margin-top:4px">الخط الأبيض = حد القبول</div>
      </div>
      <div class="tile">
        <div class="lb">🚗 أمر الحركة</div>
        <div class="vl" id="m_cmd" style="font-size:22px">متوقف ⏹</div>
        <div class="sb" id="m_cmd_s">ما في هدف</div>
        <button id="btn_drive" class="ghost" onclick="toggleDrive()">▶ تشغيل الحركة</button>
      </div>
    </div>

    <div class="card">
      <div class="card-h">
        <h2>⚖️ توازن العجلات</h2>
        <span class="badge" id="bal_badge">255 / 255</span>
      </div>
      <div class="metrics">
        <div class="tile" style="text-align:center">
          <div class="lb">العجلة اليسار</div>
          <div class="vl" id="bal_l">255</div>
          <div class="btns" style="justify-content:center">
            <button class="ghost" onclick="adjBal('l',-5)">−5</button>
            <button class="ghost" onclick="adjBal('l',5)">+5</button>
          </div>
        </div>
        <div class="tile" style="text-align:center">
          <div class="lb">العجلة اليمين</div>
          <div class="vl" id="bal_r">255</div>
          <div class="btns" style="justify-content:center">
            <button class="ghost" onclick="adjBal('r',-5)">−5</button>
            <button class="ghost" onclick="adjBal('r',5)">+5</button>
          </div>
        </div>
      </div>
      <div class="btns" style="margin-top:10px">
        <button class="grow" onclick="testStraight()">🧪 جرّبي مستقيم ثانيتين</button>
        <button class="ghost" onclick="setBal(255,255)">↺ 255 / 255</button>
      </div>
      <div class="msg" style="color:var(--mut)">255 هي أقصى قوة. إذا بتميل لجهة، نزّلي العجلة التانية (عكس جهة الميلان) −5 كل مرة وجرّبي، لحد ما تمشي مستقيم.</div>
    </div>

    <div class="card">
      <div class="card-h">
        <h2>🚀 السرعة حسب المسافة</h2>
        <span class="badge" id="spd_badge">—</span>
      </div>
      <div class="btns" style="margin-bottom:10px">
        <button id="s_on" class="grow ghost" onclick="setSpeed({on:1})">شغّالة (بعيد أسرع، قريب أبطأ)</button>
        <button id="s_off" class="grow ghost" onclick="setSpeed({on:0})">موقفة (دايماً أقصى سرعة)</button>
      </div>
      <div class="metrics">
        <div class="tile" style="text-align:center">
          <div class="lb">قوة المشي البطيء (قريب)</div>
          <div class="vl" id="s_pwr">200</div>
          <div class="btns" style="justify-content:center">
            <button class="ghost" onclick="adjSpeed('pwr',-10)">−10</button>
            <button class="ghost" onclick="adjSpeed('pwr',10)">+10</button>
          </div>
        </div>
        <div class="tile" style="text-align:center">
          <div class="lb">أقل من هيك = بطيء (م)</div>
          <div class="vl" id="s_near">1.4</div>
          <div class="btns" style="justify-content:center">
            <button class="ghost" onclick="adjSpeed('near',-0.1)">−0.1</button>
            <button class="ghost" onclick="adjSpeed('near',0.1)">+0.1</button>
          </div>
        </div>
        <div class="tile" style="text-align:center">
          <div class="lb">أكثر من هيك = أقصى سرعة (م)</div>
          <div class="vl" id="s_far">2.0</div>
          <div class="btns" style="justify-content:center">
            <button class="ghost" onclick="adjSpeed('far',-0.1)">−0.1</button>
            <button class="ghost" onclick="adjSpeed('far',0.1)">+0.1</button>
          </div>
        </div>
      </div>
      <div class="msg" style="color:var(--mut)">بعيدة = 255 (أسرع إشي). قريبة = القوة البطيئة. وعند 1 متر بتوقف. إذا الشنطة وهي قريبة ما بتتحرك على الأرض، زيدي القوة البطيئة +10.</div>
    </div>

    <div class="card">
      <div class="card-h">
        <h2>🔄 ضبط اللف</h2>
        <span class="badge" id="turn_badge">—</span>
      </div>
      <div class="btns" style="margin-bottom:10px">
        <button id="m_pivot" class="grow ghost" onclick="setTurn({mode:'pivot'})">بالمكان (عجلة لقدام وعجلة لورا)</button>
        <button id="m_swing" class="grow ghost" onclick="setTurn({mode:'swing'})">بعجلة وحدة (الثانية واقفة)</button>
      </div>
      <div class="metrics">
        <div class="tile" style="text-align:center">
          <div class="lb">قوة اللف</div>
          <div class="vl" id="t_pwr">255</div>
          <div class="btns" style="justify-content:center">
            <button class="ghost" onclick="adjTurn('pwr',-10)">−10</button>
            <button class="ghost" onclick="adjTurn('pwr',10)">+10</button>
          </div>
        </div>
        <div class="tile" style="text-align:center">
          <div class="lb">أطول نبضة لف وقت التتبع (ثانية)</div>
          <div class="vl" id="t_pmax">0.30</div>
          <div class="btns" style="justify-content:center">
            <button class="ghost" onclick="adjTurn('pmax',-0.05)">−0.05</button>
            <button class="ghost" onclick="adjTurn('pmax',0.05)">+0.05</button>
          </div>
        </div>
      </div>
      <div class="btns" style="margin-top:10px">
        <button class="grow" onclick="testTurn(-1)">🧪 ↺ لف يسار ثانية</button>
        <button class="grow" onclick="testTurn(1)">🧪 ↻ لف يمين ثانية</button>
      </div>
      <div class="msg" style="color:var(--mut)">جرّبي على الأرض: إذا العجلات بتلف والشنطة ما بتلف، جرّبي الطريقة الثانية. وإذا ما زبط، زيدي "أطول نبضة" لأنه النبضة القصيرة ممكن ما تلحق تحرّك الشنطة.</div>
    </div>

    <div class="card">
      <div class="card-h">
        <h2>📸 تسجيل المستخدم</h2>
        <span id="reg_badge" class="badge bad">غير مسجّل</span>
      </div>

      <div class="steps">
        <div class="step" id="s0"><img class="th" alt=""><b>1</b>أمام</div>
        <div class="step" id="s1"><img class="th" alt=""><b>2</b>خلف</div>
        <div class="step" id="s2"><img class="th" alt=""><b>3</b>جنب أيمن</div>
        <div class="step" id="s3"><img class="th" alt=""><b>4</b>جنب أيسر</div>
      </div>
      <div id="th_hint" class="msg" style="display:none;color:var(--mut);margin:-4px 0 10px">📷 هاي الصور اللي التقطتها الكاميرا — اضغطي على أي صورة لتكبيرها</div>

      <div id="instr" class="instr">
        <div class="sm" id="instr_sm"></div>
        <div class="cd" id="instr_cd"></div>
        <div class="big" id="instr_big"></div>
      </div>

      <ul id="tips" class="tips">
        <li>سجّلي من كاميرا الشنطة نفسها وهي على الأرض، وإنتِ على بعد 1.5–2 متر (نفس وضع التتبع).</li>
        <li>خلي حالك لحالك بالصورة، وبإضاءة كويسة.</li>
        <li>بكل خطوة عندك 3 ثواني استعداد، وما بتتصور الصورة إلا لما تكوني بالوضعية الصح.</li>
      </ul>

      <div class="btns">
        <button id="btn_main" class="grow" onclick="onMain()" disabled>ابدأ التسجيل</button>
        <button id="btn_clear" class="ghost" onclick="resetRef()" style="display:none">🗑️ مسح التسجيل</button>
      </div>
    </div>

    <details id="caldet" class="card">
      <summary>
        <h2>📐 معايرة المسافة</h2>
        <span id="cal_badge" class="badge bad">غير معايرة</span>
      </summary>
      <div class="body">
        <ol class="cal-steps">
          <li>قيسي بالمتر مسافة من الكاميرا (يفضّل 1م ثم 2م ثم 3م).</li>
          <li>وقفي بنص الصورة وثابتة لحد ما تظهر النقاط الصفراء على جسمك.</li>
          <li>اكتبي المسافة الحقيقية واضغطي "إضافة نقطة". كرري لكل مسافة.</li>
        </ol>
        <div id="cal_meas" class="meas no">⏳ ما في قياس حاليا</div>
        <div class="row">
          <label>طولك الحقيقي (م)<input id="cal_h" value="1.70" inputmode="decimal"></label>
          <label>المسافة الحقيقية (م)<input id="cal_d" value="1.0" inputmode="decimal"></label>
        </div>
        <div id="chips" class="chips"></div>
        <div class="btns">
          <button id="btn_cal" class="grow" onclick="calib()" disabled>➕ إضافة نقطة</button>
          <button class="ghost" onclick="calibReset()">🗑️ مسح النقاط</button>
        </div>
        <div id="cres" class="msg"></div>
      </div>
    </details>

  </div>
</div>

<footer id="diag">—</footer>
</div>

<div id="lb" onclick="this.style.display='none'"><img id="lb_img" alt=""></div>
<div id="toast"></div>

<script>
const $ = id => document.getElementById(id);
const KINDS = {
  loading:  {ic:'⏳', cls:'st-loading'},
  idle:     {ic:'🙋', cls:'st-idle'},
  register: {ic:'📸', cls:'st-register'},
  warn:     {ic:'⚠️', cls:'st-warn'},
  search:   {ic:'🔍', cls:'st-search'},
  tracking: {ic:'✅', cls:'st-tracking'},
  lost:     {ic:'🛑', cls:'st-lost'}
};
let cur = null, lastShots = 0, audioCtx = null, wasActive = false;
let fails = 0, calOpened = false, lastPts = '', toastT = null, thumbVer = -1;
document.querySelectorAll('.step .th').forEach(im => im.addEventListener('click', () => {
  $('lb_img').src = im.src; $('lb').style.display = 'flex';
}));

function clean(s){ return (s || '').replace(/[✅⚠️🔄]/g, '').replace(/\s+/g, ' ').trim(); }

function beep(freq, ms){
  try{
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const o = audioCtx.createOscillator(); o.frequency.value = freq;
    o.connect(audioCtx.destination); o.start(); setTimeout(() => o.stop(), ms);
  }catch(e){}
}
function toast(t){
  const e = $('toast'); e.textContent = t; e.classList.add('show');
  clearTimeout(toastT); toastT = setTimeout(() => e.classList.remove('show'), 3500);
}
function setHero(kind, ic, head, note){
  const k = KINDS[kind] || KINDS.idle;
  $('hero').className = 'hero ' + k.cls;
  $('hero_ic').textContent = ic || k.ic;
  $('hero_head').textContent = head;
  $('hero_note').textContent = note || '';
}
function setConn(cls, t){
  $('conn').className = 'pill ' + cls;
  $('conn_t').textContent = t;
}
function nextDist(pts){
  for(const t of [1, 2, 3]){ if(!pts.some(p => Math.abs(p - t) < 0.15)) return t; }
  return null;
}

/* ---------------- أوامر ---------------- */
async function startReg(){
  lastShots = 0; beep(1, 10);
  try{ await fetch('/register?t=' + Date.now(), {cache:'no-store'}); }
  catch(e){ toast('❌ الطلب ما وصل للجهاز'); }
}
async function resetRef(){
  try{ await fetch('/reset?t=' + Date.now(), {cache:'no-store'}); }
  catch(e){ toast('❌ الطلب ما وصل للجهاز'); }
}
function onMain(){ return (cur && cur.reg_active) ? resetRef() : startReg(); }

async function calib(){
  const m = $('cres');
  try{
    const r = await fetch('/calibrate?d=' + encodeURIComponent($('cal_d').value) +
                          '&h=' + encodeURIComponent($('cal_h').value));
    const j = await r.json();
    if(j.ok){
      m.className = 'msg ok';
      m.textContent = 'تمت إضافة النقطة ✅ (عدد النقاط: ' + j.n + ')';
    }else{
      m.className = 'msg bad';
      m.textContent = j.error || 'صار خطأ';
    }
  }catch(e){
    m.className = 'msg bad'; m.textContent = 'الطلب ما وصل للجهاز';
  }
}
async function calibReset(){
  if(!confirm('مسح كل نقاط المعايرة؟')) return;
  const m = $('cres');
  try{
    await fetch('/calibrate_reset');
    m.className = 'msg ok'; m.textContent = 'تم مسح كل نقاط المعايرة';
  }catch(e){
    m.className = 'msg bad'; m.textContent = 'الطلب ما وصل للجهاز';
  }
}
async function setBal(l, r){
  try{ await fetch('/balance?l=' + l + '&r=' + r + '&t=' + Date.now(), {cache:'no-store'}); }
  catch(e){ toast('❌ الطلب ما وصل للجهاز'); }
}
function adjBal(side, delta){
  const mo = (cur && cur.motor) || {l_pwr:255, r_pwr:255};
  let l = mo.l_pwr, r = mo.r_pwr;
  if(side === 'l') l += delta; else r += delta;
  l = Math.max(150, Math.min(255, l)); r = Math.max(150, Math.min(255, r));
  if(cur && cur.motor){ cur.motor.l_pwr = l; cur.motor.r_pwr = r; }
  setBal(l, r);
}
async function setTurn(o){
  const q = Object.keys(o).map(k => k + '=' + encodeURIComponent(o[k])).join('&');
  try{ await fetch('/turn_cfg?' + q + '&t=' + Date.now(), {cache:'no-store'}); }
  catch(e){ toast('❌ الطلب ما وصل للجهاز'); }
}
function adjTurn(key, delta){
  const mo = (cur && cur.motor) || {p_pwr:255, p_max:0.3};
  if(key === 'pwr'){
    const v = Math.max(150, Math.min(255, mo.p_pwr + delta));
    if(cur && cur.motor) cur.motor.p_pwr = v;
    setTurn({pwr: v});
  }else{
    const v = Math.max(0.10, Math.min(1.0, Math.round((mo.p_max + delta) * 100) / 100));
    if(cur && cur.motor) cur.motor.p_max = v;
    setTurn({pmax: v});
  }
}
async function setSpeed(o){
  const q = Object.keys(o).map(k => k + '=' + encodeURIComponent(o[k])).join('&');
  try{ await fetch('/speed_cfg?' + q + '&t=' + Date.now(), {cache:'no-store'}); }
  catch(e){ toast('❌ الطلب ما وصل للجهاز'); }
}
function adjSpeed(key, delta){
  const mo = (cur && cur.motor) || {s_pwr:200, s_near:1.4, s_far:2.0};
  if(key === 'pwr'){
    const v = Math.max(150, Math.min(255, mo.s_pwr + delta));
    if(cur && cur.motor) cur.motor.s_pwr = v;
    setSpeed({pwr: v});
  }else{
    const v = Math.round((mo['s_' + key] + delta) * 10) / 10;
    if(cur && cur.motor) cur.motor['s_' + key] = v;
    setSpeed({[key]: v});
  }
}
async function testTurn(side){
  try{ await fetch('/test_turn?side=' + (side > 0 ? 1 : -1) + '&t=' + Date.now(), {cache:'no-store'}); toast('🧪 بتلف ثانية…'); }
  catch(e){ toast('❌ الطلب ما وصل للجهاز'); }
}
async function testStraight(){
  try{ await fetch('/test_straight?t=' + Date.now(), {cache:'no-store'}); toast('🧪 بتمشي مستقيم ثانيتين…'); }
  catch(e){ toast('❌ الطلب ما وصل للجهاز'); }
}
async function toggleDrive(){
  const on = !(cur && cur.motor && cur.motor.enabled);
  try{ await fetch('/drive?on=' + (on ? 1 : 0) + '&t=' + Date.now(), {cache:'no-store'}); }
  catch(e){ toast('❌ الطلب ما وصل للجهاز'); }
}

/* ---------------- العرض ---------------- */
function render(d){
  const reg = !!d.reg_active;
  const paused = reg && d.pause_left > 0;
  const tracking = d.kind === 'tracking' && d.dist_m !== null && d.dist_m !== undefined;

  // --- الشريط العلوي ---
  if(!d.ready) setConn('wait', 'الذكاء الاصطناعي يتحمّل…');
  else setConn('ok', 'الجهاز شغّال');

  // --- الحالة الرئيسية ---
  if(!d.ready){
    setHero('loading', '⏳', 'جاري تحميل النماذج…', 'ممكن تاخد دقيقة بأول تشغيل');
  }else if(reg){
    const step = Math.min(d.reg_done + 1, d.reg_total);
    const head = 'جاري التسجيل — الخطوة ' + step + ' من ' + d.reg_total;
    if(paused) setHero('register', '⏳', head, 'استعدي… التصوير بعد ' + Math.ceil(d.pause_left) + ' ثواني (لسا ما صورت)');
    else if(d.reg_warn) setHero('lost', '👀', head, 'ما شفتك! قفي كاملة قدام الكاميرا (راس وقدمين)');
    else if(d.reg_hint) setHero('warn', '🔄', head, d.reg_hint + ' — ما صورت لسا');
    else setHero('tracking', '📸', head, 'ثبتي مكانك… جاري التصوير');
  }else{
    setHero(d.kind, null, clean(d.status), d.note || (d.kind === 'idle' && !d.registered ? 'اضغطي "ابدأ التسجيل" عشان أتعرف عليكِ' : ''));
  }

  // --- المقاييس ---
  if(tracking){
    $('m_dist').textContent = (d.reliable === false ? '≤ ' : '') + d.dist_m.toFixed(2);
    $('m_dist_u').style.display = '';
    const notes = [];
    if(!d.calibrated) notes.push('تقريبية (غير معايرة)');
    if(d.reliable === false) notes.push('جزء من جسمك بس ظاهر');
    else if(d.method_ar) notes.push('القياس: ' + d.method_ar);
    $('m_dist_s').textContent = notes.join(' • ');
    $('m_dir').textContent = d.dir;
    $('m_ang').textContent = d.angle + '°';
    const a = Math.max(-45, Math.min(45, d.angle));
    $('mark').style.display = 'block';
    $('mark').style.left = (50 + a / 45 * 50) + '%';
  }else{
    $('m_dist').textContent = '—'; $('m_dist_u').style.display = 'none';
    $('m_dist_s').textContent = 'بتظهر لما أتعرف عليكِ';
    $('m_dir').textContent = '—'; $('m_ang').textContent = '';
    $('mark').style.display = 'none';
  }
  const showSim = d.registered && !reg && d.sim > 0;
  $('m_sim').textContent = showSim ? d.sim : '—';
  $('m_sim_u').style.display = showSim ? '' : 'none';
  const sb = $('sim_bar');
  sb.style.width = (showSim ? Math.min(100, d.sim) : 0) + '%';
  sb.style.background = d.sim >= 78 ? 'var(--ok)' : 'var(--warn)';

  // --- التسجيل ---
  const rb = $('reg_badge');
  if(reg){ rb.className = 'badge warn'; rb.textContent = 'جاري التسجيل'; }
  else if(d.registered){ rb.className = 'badge ok'; rb.textContent = 'مسجّل ✅'; }
  else { rb.className = 'badge bad'; rb.textContent = 'غير مسجّل'; }

  for(let i = 0; i < 4; i++){
    const s = $('s' + i);
    let c = 'step';
    if(!reg && d.registered) c += ' done';
    else if(reg && i < d.reg_done) c += ' done';
    else if(reg && i === d.reg_done) c += ' cur';
    if((d.thumbs || []).includes(i)) c += ' has';
    s.className = c;
  }
  if(thumbVer !== d.thumb_ver){
    thumbVer = d.thumb_ver;
    for(let i = 0; i < 4; i++){
      if((d.thumbs || []).includes(i)) $('s' + i).querySelector('.th').src = '/thumb/' + i + '?v=' + thumbVer;
    }
  }
  $('th_hint').style.display = (d.thumbs || []).length ? '' : 'none';

  const ins = $('instr');
  ins.style.display = reg ? 'block' : 'none';
  if(reg){
    $('instr_big').textContent = clean(d.reg_text);
    if(paused){
      $('instr_sm').textContent = 'استعدي — لسا ما صورت';
      $('instr_cd').textContent = Math.ceil(d.pause_left);
    }else{
      $('instr_cd').textContent = '';
      $('instr_sm').textContent = d.reg_warn ? 'ما شفتك' : (d.reg_hint ? 'عدّلي وضعيتك' : 'ثبتي…');
    }
  }
  $('tips').style.display = (!reg && !d.registered) ? '' : 'none';

  const bm = $('btn_main');
  bm.disabled = !d.ready;
  bm.className = 'grow' + (reg ? ' danger' : '');
  bm.textContent = reg ? 'إلغاء التسجيل' : (d.registered ? 'إعادة التسجيل' : 'ابدأ التسجيل');
  $('btn_clear').style.display = (d.registered && !reg) ? '' : 'none';

  if(wasActive && !reg && d.registered){ toast('تم التسجيل بنجاح ✅ جاهزة للتتبع'); beep(1200, 250); }
  wasActive = reg;
  if(d.shots > lastShots) beep(900, 150);
  lastShots = d.shots;

  // --- المعايرة ---
  const pts = d.calib_points || [];
  const cb = $('cal_badge');
  if(d.calibrated && pts.length >= 3){ cb.className = 'badge ok'; cb.textContent = 'معايرة كاملة ✅ (' + pts.length + ' نقاط)'; }
  else if(d.calibrated && pts.length){ cb.className = 'badge warn'; cb.textContent = 'جزئية — أضيفي ' + (3 - pts.length) + ' نقطة كمان'; }
  else if(d.calibrated){ cb.className = 'badge warn'; cb.textContent = 'قديمة (نقطة وحدة) — أضيفي 3 نقاط'; }
  else { cb.className = 'badge bad'; cb.textContent = 'غير معايرة — الأرقام تقريبية'; }
  if(!calOpened && d.ready){ calOpened = true; if(!d.calibrated) $('caldet').open = true; }

  const key = pts.join(',');
  if(key !== lastPts){
    lastPts = key;
    $('chips').innerHTML = pts.map(p => '<span class="chip">' + p.toFixed(2) + ' م</span>').join('');
    const nd = nextDist(pts);
    if(nd !== null && document.activeElement !== $('cal_d')) $('cal_d').value = nd.toFixed(1);
  }
  const has = d.scale !== null && d.scale !== undefined;
  const cm = $('cal_meas');
  cm.className = 'meas ' + (has ? 'ok' : 'no');
  cm.textContent = has ? ('✅ القياس جاهز (مقياس الجسم ' + d.scale + ' بكسل)')
                       : '⏳ ما في قياس — وقفي بنص الصورة كاملة لحد ما تظهر النقاط الصفراء';
  $('btn_cal').disabled = !has;

  // --- أخطاء وتشخيص ---
  const er = $('err');
  if(d.err){ er.style.display = 'block'; $('err_t').textContent = d.err; }
  else er.style.display = 'none';
  $('diag').textContent = 'أشخاص ظاهرين: ' + d.people + '  •  زمن الكشف: ' + d.det_ms + ' ms  •  focal: ' + d.focal;

  // --- الماتورات ---
  const mo = d.motor || {};
  if(mo.l_pwr !== undefined){
    $('bal_l').textContent = mo.l_pwr; $('bal_r').textContent = mo.r_pwr;
    $('bal_badge').textContent = 'يسار ' + mo.l_pwr + ' / يمين ' + mo.r_pwr;
    $('t_pwr').textContent = mo.p_pwr; $('t_pmax').textContent = Number(mo.p_max).toFixed(2);
    $('m_pivot').className = 'grow' + (mo.p_mode === 'pivot' ? '' : ' ghost');
    $('m_swing').className = 'grow' + (mo.p_mode === 'swing' ? '' : ' ghost');
    $('turn_badge').textContent = (mo.p_mode === 'pivot' ? 'بالمكان' : 'بعجلة وحدة') + ' • ' + mo.p_pwr;
    $('s_pwr').textContent = mo.s_pwr;
    $('s_near').textContent = Number(mo.s_near).toFixed(1);
    $('s_far').textContent = Number(mo.s_far).toFixed(1);
    $('s_on').className = 'grow' + (mo.s_on ? '' : ' ghost');
    $('s_off').className = 'grow' + (mo.s_on ? ' ghost' : '');
    $('spd_badge').textContent = (mo.s_on ? 'شغّالة' : 'موقفة') + ' • السرعة الآن ' + (mo.spd || 0) + '%';
  }
  const bd = $('btn_drive');
  bd.textContent = mo.enabled ? '⏹ إيقاف الحركة' : '▶ تشغيل الحركة';
  bd.className = mo.enabled ? 'danger' : 'ghost';
  if(!mo.connected){
    $('m_cmd').textContent = '🔌 غير موصول';
    $('m_cmd_s').textContent = mo.err || 'الأردوينو مش موصول';
  }else if(!mo.enabled){
    $('m_cmd').textContent = 'موقفة ⏸';
    $('m_cmd_s').textContent = 'اضغطي "تشغيل الحركة"';
  }else{
    $('m_cmd').textContent = (mo.l || mo.r) ? 'يتحرك ▶' : 'واقف ⏹';
    $('m_cmd_s').textContent = 'L ' + mo.l + ' • R ' + mo.r + ' — ' + mo.why;
  }
}

function showOffline(){
  setConn('off', 'انقطع الاتصال');
  setHero('lost', '📡', 'انقطع الاتصال بالجهاز', 'تأكدي إنه شغّال وإنك على نفس الشبكة — برجع أحاول تلقائياً');
}

async function poll(){
  try{
    const r = await fetch('/info', {cache:'no-store'});
    const d = await r.json();
    if(fails >= 3) $('video').src = '/video?t=' + Date.now();
    fails = 0; cur = d; render(d);
  }catch(e){
    fails++;
    if(fails >= 3) showOffline();
  }
  setTimeout(poll, 300);
}
$('video').addEventListener('error', () => setTimeout(() => { $('video').src = '/video?t=' + Date.now(); }, 2000));
poll();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return INDEX_HTML


@app.route("/video")
def video():
    stream_state["token"] += 1
    return Response(generate(stream_state["token"]),
                    mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-store"})


@app.route("/snapshot")
def snapshot():
    """Return the latest camera frame as one JPEG for native mobile Image views."""
    with cond:
        data = shared["jpeg"]
    if data is None:
        return Response(status=503, headers={"Cache-Control": "no-store"})
    return Response(data, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


@app.route("/register")
def register():
    print(">>> REGISTER pressed", flush=True)
    msg, cnt, en = REGISTER_STEPS[0]
    with lock:                                   # ردة فعل فورية قبل ما يرد الذكاء الاصطناعي
        state["reg"] = {"active": True, "pause_until": time.time() + PAUSE_SECONDS, "en": en,
                        "msg": msg, "warn": False, "done": 0,
                        "total": sum(x[1] for x in REGISTER_STEPS), "shots": 0,
                        "hint": "", "hint_ar": "", "registered": False}
        state["last_shots"] = 0
        state["overlay"], state["kp_draw"] = [], []
        state["info"] = make_info(msg, kind="register")
        state["thumbs"] = {}
        state["thumb_ver"] += 1
    send_cmd("register")
    return jsonify({"ok": True})


@app.route("/reset")
def reset():
    with lock:
        state["reg"] = dict(REG_IDLE)
        state["last_shots"] = 0
        state["overlay"], state["kp_draw"] = [], []
        state["info"] = make_info("غير مسجّل")
        state["thumbs"] = {}
        state["thumb_ver"] += 1
    send_cmd("reset")
    return jsonify({"ok": True})


@app.route("/thumb/<int:i>")
def thumb(i):
    with lock:
        data = state["thumbs"].get(i)
    if data is None:
        return Response(status=404)
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@app.route("/calibrate")
def calibrate():
    """بتضيف نقطة معايرة: (مقياس جسمك الحالي) <-> (المسافة الحقيقية اللي كتبتيها)."""
    try:
        d = float(request.args["d"])
        hm = float(request.args["h"])
        assert 0.3 <= d <= 15 and 0.5 <= hm <= 2.5
    except Exception:
        return jsonify({"ok": False, "error": "قيم غير صحيحة"}), 400
    with lock:
        meas = state["meas"]
        calib = dict(state["calib"])
    if not meas or time.time() - meas["t"] > 2.0:
        return jsonify({"ok": False,
                        "error": "ما في قياس حديث: لازم أشوفك بالفيديو والنقاط الصفراء ظاهرة على جسمك"}), 400
    pts = list(calib["points"])
    if abs(hm - calib["person_h"]) > 1e-6:
        pts = []                                   # الطول تغيّر -> النقاط القديمة ما بتنفع
    inv = hm / meas["s"]
    pts = [p for p in pts if abs(p[1] - d) > 0.15 and abs(p[0] - inv) > 1e-6]
    pts.append((inv, d))
    pts.sort()
    if any(pts[i][1] >= pts[i + 1][1] for i in range(len(pts) - 1)):
        return jsonify({"ok": False,
                        "error": "القياس مش منطقي مع النقاط السابقة (بعيد أكبر من قريب). وقفي بالنص وثابتة وعيدي، أو امسحي النقاط وابدأي من جديد"}), 400
    calib.update(points=pts, person_h=hm, calibrated=True,
                 focal_px=float(np.median([z / i for i, z in pts])))
    with lock:
        state["calib"] = calib
        save_calib()
    send_cmd("set_calib", calib)
    return jsonify({"ok": True, "method": meas["method"], "n": len(pts),
                    "points": [round(z, 2) for _, z in pts]})


@app.route("/calibrate_reset")
def calibrate_reset():
    calib = {"focal_px": focal_from_fov(G["out_w"], G["hfov"]), "person_h": PERSON_REAL_HEIGHT_M,
             "points": [], "calibrated": False}
    with lock:
        state["calib"] = calib
    try:
        os.remove(CALIB_FILE)
    except OSError:
        pass
    send_cmd("set_calib", calib)
    return jsonify({"ok": True})


@app.route("/balance")
def balance():
    try:
        l = int(request.args.get("l", MOTOR["l_pwr"]))
        r = int(request.args.get("r", MOTOR["r_pwr"]))
    except ValueError:
        return jsonify({"ok": False}), 400
    with lock:
        MOTOR["l_pwr"] = max(BAL_MIN, min(255, l))
        MOTOR["r_pwr"] = max(BAL_MIN, min(255, r))
        save_balance()
    print(f">>> BALANCE L={MOTOR['l_pwr']} R={MOTOR['r_pwr']}", flush=True)
    return jsonify({"ok": True, "l": MOTOR["l_pwr"], "r": MOTOR["r_pwr"]})


@app.route("/test_straight")
def test_straight():
    with lock:
        MOTOR["test_kind"] = "straight"
        MOTOR["test_until"] = time.time() + TEST_SEC
    print(">>> TEST STRAIGHT", flush=True)
    return jsonify({"ok": True})


@app.route("/turn_cfg")
def turn_cfg():
    with lock:
        try:
            if "pwr" in request.args:
                MOTOR["p_pwr"] = max(BAL_MIN, min(255, int(request.args["pwr"])))
            if "pmax" in request.args:
                MOTOR["p_max"] = round(max(0.10, min(1.0, float(request.args["pmax"]))), 2)
            if request.args.get("mode") in ("pivot", "swing"):
                MOTOR["p_mode"] = request.args["mode"]
        except ValueError:
            return jsonify({"ok": False}), 400
        save_balance()
    print(f">>> TURN mode={MOTOR['p_mode']} pwr={MOTOR['p_pwr']} pulse={MOTOR['p_max']}", flush=True)
    return jsonify({"ok": True})


@app.route("/weight")
def weight():
    with lock:
        return jsonify(weight_status())


@app.route("/weight_tare")
def weight_tare():
    """تصفير: الشنطة فاضية فوق الميزان -> الأردوينو بيصفّر وبيحفظ."""
    with lock:
        if not weight_connected():
            return jsonify({"ok": False, "error": "الميزان مش موصول"}), 400
        ARD_TX.append("z")
    print(">>> WEIGHT TARE (z)", flush=True)
    return jsonify({"ok": True})


@app.route("/weight_cal")
def weight_cal():
    """معايرة: في وزن معروف (kg) بالشنطة -> الأردوينو بيحسب المعامل وبيحفظه بالـ EEPROM."""
    try:
        kg = float(request.args["kg"])
        assert 0.1 <= kg <= 100
    except Exception:
        return jsonify({"ok": False, "error": "اكتبي الوزن المعروف بالكيلو (من 0.1 لـ 100)"}), 400
    with lock:
        if not weight_connected():
            return jsonify({"ok": False, "error": "الميزان مش موصول"}), 400
        MOTOR["enabled"] = False                     # الحركة لازم توقف وقت المعايرة
        ARD_TX.append(f"K,{kg * 1000:.0f}")
    print(f">>> WEIGHT CAL {kg} kg", flush=True)
    return jsonify({"ok": True})


@app.route("/weight_cfg")
def weight_cfg():
    with lock:
        try:
            if "bag" in request.args:
                WEIGHT["bag_kg"] = round(max(0.0, min(20.0, float(request.args["bag"]))), 2)
            if "limit" in request.args:
                WEIGHT["limit"] = round(max(1.0, min(100.0, float(request.args["limit"]))), 1)
        except ValueError:
            return jsonify({"ok": False, "error": "أرقام غلط"}), 400
        save_weight()
    return jsonify({"ok": True, "bag_kg": WEIGHT["bag_kg"], "limit": WEIGHT["limit"]})


@app.route("/speed_cfg")
def speed_cfg():
    with lock:
        try:
            if "pwr" in request.args:
                MOTOR["s_pwr"] = max(BAL_MIN, min(255, int(request.args["pwr"])))
            if "near" in request.args:
                MOTOR["s_near"] = round(max(1.1, min(4.0, float(request.args["near"]))), 1)
            if "far" in request.args:
                MOTOR["s_far"] = round(max(1.2, min(6.0, float(request.args["far"]))), 1)
            if MOTOR["s_far"] < MOTOR["s_near"] + 0.2:
                MOTOR["s_far"] = round(MOTOR["s_near"] + 0.2, 1)
            if "on" in request.args:
                MOTOR["s_on"] = request.args["on"] == "1"
        except ValueError:
            return jsonify({"ok": False}), 400
        save_balance()
    print(f">>> SPEED on={MOTOR['s_on']} slow={MOTOR['s_pwr']} near={MOTOR['s_near']} far={MOTOR['s_far']}", flush=True)
    return jsonify({"ok": True})


@app.route("/test_turn")
def test_turn():
    side = 1 if request.args.get("side", "1") == "1" else -1
    with lock:
        MOTOR.update(test_kind="turn", test_side=side, test_until=time.time() + TEST_TURN_SEC)
    print(">>> TEST TURN", side, flush=True)
    return jsonify({"ok": True})


@app.route("/drive")
def drive():
    on = request.args.get("on") == "1"
    with lock:
        MOTOR["enabled"] = on
        MOTOR["moving"] = False
    print(">>> DRIVE", "ON" if on else "OFF", flush=True)
    return jsonify({"ok": True, "enabled": on})


@app.route("/info")
def info():
    with lock:
        d = dict(state["info"])
        reg = state["reg"]
        d["reg_active"] = reg["active"]
        d["pause_left"] = max(0.0, reg["pause_until"] - time.time()) if reg["active"] else 0
        d["reg_done"], d["reg_total"], d["shots"] = reg["done"], reg["total"], reg["shots"]
        d["reg_text"], d["reg_warn"] = reg["msg"], reg["warn"]
        d["reg_hint"] = reg.get("hint_ar", "")
        d["registered"] = reg.get("registered", False)
        d["ready"] = state["ready"]
        d["thumbs"] = sorted(state["thumbs"].keys())
        d["thumb_ver"] = state["thumb_ver"]
        d["focal"] = round(state["calib"]["focal_px"], 1)
        d["calibrated"] = state["calib"]["calibrated"]
        d["calib_points"] = [round(z, 2) for _, z in sorted(state["calib"]["points"])]
        m = state["meas"]
        d["scale"] = round(m["s"]) if m and time.time() - m["t"] < 2.0 else None
        d.update(people=state["diag"]["people"], det_ms=state["diag"]["det_ms"],
                 err=state["diag"]["err"])
        d["motor"] = {k: MOTOR[k] for k in ("enabled", "connected", "port", "err", "l", "r", "why", "l_pwr", "r_pwr",
                                                  "p_pwr", "p_mode", "p_max",
                                                  "s_on", "s_pwr", "s_near", "s_far", "spd")}
        w = weight_status()
        d["weight_info"] = w
        d["weight"] = w["kg"]                     # للتطبيق: الوزن الكلي بالكيلو
        return jsonify(d)


# ===================== التشغيل =====================
def pick_wide_mode(cam):
    modes = cam.sensor_modes
    area = lambda m: m["crop_limits"][2] * m["crop_limits"][3]
    max_area = max(area(m) for m in modes)
    full = [m for m in modes if area(m) >= max_area * 0.99]
    return min(full, key=lambda m: m["size"][0] * m["size"][1])


def detect_hfov(picam2):
    if CAMERA_HFOV_DEG:
        return CAMERA_HFOV_DEG, "manual"
    model = str(picam2.camera_properties.get("Model", "")).lower()
    for key, fov in (("imx708_wide", 102.0), ("imx708", 66.0), ("imx219", 62.2), ("ov5647", 53.5)):
        if key in model:
            return fov, model
    return 66.0, model + " (غير معروف - لازم معايرة!)"


def main():
    from picamera2 import Picamera2

    picam2 = Picamera2()
    mode = pick_wide_mode(picam2)
    mw, mh = mode["size"]
    out_w = STREAM_W
    out_h = int(STREAM_W * mh / mw) // 2 * 2
    print(f"Sensor mode: {mode['size']}  ->  output: {out_w}x{out_h}")
    picam2.configure(picam2.create_video_configuration(
        main={"format": "RGB888", "size": (out_w, out_h)},      # ترتيب BGR (مناسب لـ OpenCV)
        sensor={"output_size": mode["size"], "bit_depth": mode["bit_depth"]},
        controls={"FrameDurationLimits": (33333, 33333), "AwbEnable": False,
                  "ColourGains": (1.8, 1.5)},
        buffer_count=4, queue=False))
    picam2.start()
    try:
        picam2.set_controls({"ScalerCrop": (0, 0, *picam2.camera_properties["PixelArraySize"])})
    except Exception as e:
        print("ScalerCrop:", e)
    time.sleep(0.5)
    print("ScalerCrop الحالي:", picam2.capture_metadata().get("ScalerCrop"))

    hfov, model = detect_hfov(picam2)
    print(f"Camera model: {model}  ->  HFOV = {hfov}°")
    G["out_w"], G["hfov"] = out_w, hfov
    calib = {"focal_px": focal_from_fov(out_w, hfov), "person_h": PERSON_REAL_HEIGHT_M,
             "points": [], "calibrated": False}
    if os.path.exists(CALIB_FILE):
        try:
            sv = json.load(open(CALIB_FILE))
            if sv.get("out_w") == out_w and sv.get("v") in (2, 3):
                calib.update(focal_px=sv["focal_px"], person_h=sv["person_h"], calibrated=True,
                             points=[tuple(p) for p in sv.get("points", [])])
                print("تم تحميل المعايرة:", calib)
        except Exception:
            pass
    state["calib"] = dict(calib)

    # ذاكرة مشتركة للفريمات + عملية الذكاء الاصطناعي
    shape = (out_h, out_w, 3)
    shm = shared_memory.SharedMemory(create=True, size=2 * int(np.prod(shape)))
    bufs = np.ndarray((2,) + shape, dtype=np.uint8, buffer=shm.buf)
    bufs[:] = 0
    ctx = mp.get_context("spawn")
    seq = ctx.Value("L", 0)
    G["cmd_q"], G["res_q"] = ctx.Queue(), ctx.Queue(maxsize=8)
    G["proc"] = ctx.Process(target=ai_main, daemon=True,
                            args=(shm.name, shape, seq, G["cmd_q"], G["res_q"], calib))
    G["proc"].start()

    threading.Thread(target=result_loop, daemon=True).start()
    threading.Thread(target=capture_loop, args=(picam2, bufs, seq), daemon=True).start()
    threading.Thread(target=motor_loop, daemon=True).start()
    try:
        app.run(host="0.0.0.0", port=5000, threaded=True)
    finally:
        MOTOR["enabled"] = False
        G["proc"].terminate()
        shm.close()
        shm.unlink()


if __name__ == "__main__":
    main()
