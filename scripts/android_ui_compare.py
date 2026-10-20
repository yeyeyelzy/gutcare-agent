#!/usr/bin/env python3
"""Deterministic, evidence-aware comparison of Android screenshots to UI baselines."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


ALGORITHM = "CIE76-sRGB-D65-v1"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def srgb_lab(rgb):
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    x = (c[..., 0] * .4124564 + c[..., 1] * .3575761 + c[..., 2] * .1804375) / .95047
    y = (c[..., 0] * .2126729 + c[..., 1] * .7151522 + c[..., 2] * .0721750)
    z = (c[..., 0] * .0193339 + c[..., 1] * .1191920 + c[..., 2] * .9503041) / 1.08883
    xyz = np.stack((x, y, z), axis=-1)
    d = 6 / 29
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4 / 29)
    return np.stack((116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])), axis=-1)


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"))


def compare(reference, actual, threshold, delta_threshold):
    rh, rw = reference.shape[:2]
    ah, aw = actual.shape[:2]
    # Fit reference to actual viewport width without distortion; compare the
    # declared scroll segment and crop only to the available viewport height.
    scaled_h = max(1, round(rh * aw / rw))
    ref = np.asarray(Image.fromarray(reference).resize((aw, scaled_h), Image.Resampling.LANCZOS))
    height = min(scaled_h, ah)
    ref, act = ref[:height, :], actual[:height, :]
    d = np.linalg.norm(srgb_lab(ref) - srgb_lab(act), axis=2)
    changed = d > delta_threshold
    heat = np.zeros((*d.shape, 3), dtype=np.uint8)
    heat[..., 0] = np.clip(d * 4, 0, 255).astype(np.uint8)
    heat[..., 1] = np.clip(220 - d * 3, 0, 220).astype(np.uint8)
    diff = np.where(changed[..., None], np.array([255, 0, 0], dtype=np.uint8), np.array([0, 0, 0], dtype=np.uint8))
    overlay = ((ref.astype(np.uint16) + act.astype(np.uint16)) // 2).astype(np.uint8)
    return {"reference": ref, "actual": act, "changed": changed, "heat": heat, "diff": diff, "overlay": overlay,
            "similarity": float(1.0 - changed.mean()), "valid_pixels": int(changed.size),
            "resized_reference_height": scaled_h, "compared_height": height,
            "cropped_reference_bottom": max(0, scaled_h - height), "cropped_actual_bottom": max(0, ah - height)}


def validate_capture(evidence, filename, image_hash, expected_activity):
    """Validate screenshot-specific evidence; malformed/missing evidence fails closed."""
    entry = (evidence or {}).get("captures", {}).get(filename)
    if not isinstance(entry, dict):
        return {"status": "missing", "reason": "no per-image capture record"}
    matching_hash = entry.get("screenshot_sha256") == image_hash
    before = entry.get("foreground_before", {})
    after = entry.get("foreground_after", {})
    def matches(state):
        return state.get("package") == expected_activity.split("/", 1)[0] and state.get("activity") == expected_activity
    valid = bool(matching_hash and matches(before) and matches(after) and entry.get("captured_at"))
    return {"status": "confirmed" if valid else "mismatch", "screenshot_sha256_matches": matching_hash,
            "foreground_before_matches": matches(before), "foreground_after_matches": matches(after),
            "captured_at": entry.get("captured_at")}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--actual-dir", type=Path, required=True)
    p.add_argument("--segments", type=Path, required=True)
    p.add_argument("--profile", type=Path, required=True)
    p.add_argument("--capture-evidence", type=Path, help="JSON with observed foreground package/activity and capture timestamp")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--threshold", type=float, default=.90)
    p.add_argument("--delta-e76", type=float, default=12)
    args = p.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    segments = json.loads(args.segments.read_text(encoding="utf-8"))
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    capture = json.loads(args.capture_evidence.read_text(encoding="utf-8")) if args.capture_evidence else None
    pages = {x["page"]: x for x in manifest["pages"]}
    expected_activity = profile.get("activity")
    if "status and navigation bars retained" not in profile.get("capture", ""):
        raise SystemExit("profile must explicitly declare status/navigation bar policy")

    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in segments["segments"]:
        page = pages[item["page"]]
        ref_path = args.manifest.parent / page["path"]
        actual_path = args.actual_dir / item["actual"]
        ref_full, actual_full = load_rgb(ref_path), load_rgb(actual_path)
        # Explicitly stated source coordinates; scaling only applies to the reference.
        scale = actual_full.shape[1] / ref_full.shape[1]
        ay = item["actual_y"]
        ref_segment = ref_full[round(item["reference_y"]):, :]
        actual_segment = actual_full[ay:, :]
        result = compare(ref_segment, actual_segment, args.threshold, args.delta_e76)
        name = item["id"]
        out = args.out / name
        out.mkdir(parents=True, exist_ok=True)
        for key, filename in (("overlay", "overlay.png"), ("diff", "diff.png"), ("heat", "heatmap.png")):
            Image.fromarray(result[key]).save(out / filename)
        passed = result["similarity"] >= args.threshold
        capture_validation = validate_capture(capture, item["actual"], sha256(actual_path), expected_activity)
        rows.append({
            "id": name, "page": item["page"], "title": page["title"], "visual_similarity": result["similarity"],
            "visual_threshold_pass": passed, "acceptance": "exploratory_only",
            "capture_validation": capture_validation,
            "delta_e76_threshold": args.delta_e76, "diff_pixels": int(result["changed"].sum()), "valid_pixels": result["valid_pixels"],
            "reference_size": [ref_full.shape[1], ref_full.shape[0]], "actual_size": [actual_full.shape[1], actual_full.shape[0]],
            "normalization": {"method": "reference_width_fit_no_stretch", "reference_scale": scale,
                              "reference_y_px": item["reference_y"], "actual_y_px": ay,
                              "system_bars": item["system_bars"], "alignment_status": "uncertain_exploratory",
                              "scroll_coverage": "top_segment_only_exploratory",
                              "compared_size": [result["actual"].shape[1], result["actual"].shape[0]],
                              "cropped_reference_bottom_px": result["cropped_reference_bottom"], "cropped_actual_bottom_px": result["cropped_actual_bottom"]},
            "roi_scores": [{"name": "full_viewport", "similarity": result["similarity"], "pixels": result["valid_pixels"]}],
            "hashes": {"reference_sha256": sha256(ref_path), "actual_sha256": sha256(actual_path)},
            "outputs": ["overlay.png", "diff.png", "heatmap.png"]})
        (out / "result.json").write_text(json.dumps(rows[-1], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"algorithm": ALGORITHM, "metric": "1 - count(CIE76 deltaE > threshold) / valid_pixels",
               "threshold": args.threshold, "delta_e76": args.delta_e76,
               "capture_evidence_sha256": sha256(args.capture_evidence) if args.capture_evidence else None,
               "acceptance_scope": "exploratory_only_top_segments_system_bar_alignment_uncertain",
               "profile_sha256": sha256(args.profile), "manifest_sha256": sha256(args.manifest),
               "segments_sha256": sha256(args.segments), "pages": rows,
               "accepted_pages": sum(x["acceptance"] == "pass" for x in rows)}
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.out), "pages": len(rows), "accepted": summary["accepted_pages"],
                      "acceptance_scope": summary["acceptance_scope"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
