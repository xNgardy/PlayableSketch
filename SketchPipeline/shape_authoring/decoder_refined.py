import json
from pathlib import Path
import cv2
import numpy as np
from .decoder import region_boxes, boundary_graph, authoring_document
from SketchPipeline.perception.structural import suppress_grid

POLICY = json.loads(Path(__file__).with_name("decoder_refined.config.json").read_text())
from .region_recovery import POLICY as REGION_POLICY

POLICY["region_reconstruction"] = REGION_POLICY


def ink_evidence(gray):
    side = max(gray.shape)
    kernel = max(3, round(side * 0.06)) | 1
    background = cv2.medianBlur(gray, kernel)
    contrast = cv2.subtract(background, gray).astype(np.float32)
    meaningful = contrast[contrast > POLICY["ink_min_contrast"]]
    reference = float(np.percentile(meaningful, 85)) if len(meaningful) else 255.0
    threshold = max(POLICY["ink_min_contrast"], reference * POLICY["ink_reference_fraction"])
    paper = float(np.percentile(gray, 90))
    ink = ((contrast >= threshold) | (gray < paper * POLICY["absolute_dark_fraction"])).astype(
        np.uint8
    )
    distance = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    positive = distance[distance > 0]
    stroke = float(np.percentile(positive, 65) * 2) if len(positive) else 1.0
    stroke = float(np.clip(stroke, 1, max(1, side / 32)))
    return (
        ink,
        stroke,
        {"background_kernel_px": kernel, "contrast_threshold": threshold, "stroke_px": stroke},
    )


def runs(values):
    changes = np.diff(np.r_[False, values, False].astype(np.int8))
    return list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)))


def ribbon(image, axis, fixed, positions, radius):
    positions = np.asarray(positions, dtype=int)
    positions = positions[(positions >= 0) & (positions < image.shape[1 - axis])]
    normals = np.arange(
        max(0, round(fixed) - radius), min(image.shape[axis], round(fixed) + radius + 1)
    )
    if not len(positions) or not len(normals):
        return np.zeros((0, 0), image.dtype)
    return image[np.ix_(normals, positions)] if axis == 0 else image[np.ix_(positions, normals)].T


def fit_axis(ink, axis, fixed, lo, hi, stroke, scale):
    search = max(2, round(min(max(ink.shape) * 0.025, max(stroke * 3, scale * 2))))
    positions = np.linspace(lo, hi, max(12, min(100, round(hi - lo)))).astype(int)
    observations = []
    for along in positions:
        patch = ribbon(ink, axis, fixed, [along], search)
        if not patch.size:
            continue
        offset = max(0, round(fixed) - search)
        groups = runs(patch[:, 0] > 0)
        if not groups:
            continue
        centers = [offset + (a + b - 1) / 2 for a, b in groups]
        observations.append(min(centers, key=lambda x: abs(x - fixed)))
    return float(np.median(observations)) if len(observations) >= 8 else float(fixed)


def tick_evidence(ink, probability, axis, fixed, endpoint, stroke, scale):
    search = max(2, round(max(stroke * 2, scale * 1.25)))
    core = max(1, round(stroke * 0.5))
    leg = max(2, round(stroke * 0.9))
    half_width = max(0, round(stroke * 0.3))
    best = None
    for along in range(round(endpoint) - search, round(endpoint) + search + 1):
        supports = []
        for sign in (-1, 1):
            normals = np.arange(
                round(fixed) + sign * (core + 1), round(fixed) + sign * (core + leg + 1), sign
            )
            normals = normals[(normals >= 0) & (normals < ink.shape[axis])]
            tangent = np.arange(
                max(0, along - half_width), min(ink.shape[1 - axis], along + half_width + 1)
            )
            patch = ink[np.ix_(normals, tangent)] if axis == 0 else ink[np.ix_(tangent, normals)].T
            supports.append(
                float(patch.max(axis=1).mean()) if patch.size and len(normals) == leg else 0.0
            )
        center = ribbon(ink, axis, fixed, [along], core)
        connected = bool(center.size and center.max())
        raw = min(supports) if connected else 0.0
        marker = (
            ribbon(probability, axis, fixed, range(along - core, along + core + 1), core)
            if probability is not None
            else None
        )
        score = float(marker.max()) if marker is not None and marker.size else 0.0
        candidate = {
            "position_px": along,
            "raw_support": raw,
            "model_center_response": score,
            "leg_support": supports,
        }
        ranking = (raw, score, -abs(along - endpoint))
        if best is None or ranking > best[0]:
            best = (ranking, candidate)
    return best[1]


def opening_candidates(
    segments, gray, probabilities, working_to_evidence, mode="paired_raw", *, align_doors=False
):
    if mode not in POLICY["semantic_modes"]:
        raise ValueError("Unsupported opening proposal mode")
    cleaned, _, grid = suppress_grid(gray)
    ink, stroke, ink_info = ink_evidence(cleaned)
    ink_info["grid_suppressed_pixels"] = grid["suppressed_pixels"]
    matrix = np.asarray(working_to_evidence, float)
    if (
        matrix.shape != (3, 3)
        or not np.isfinite(matrix).all()
        or (not np.allclose(matrix[2], [0, 0, 1]))
        or (abs(matrix[0, 1]) + abs(matrix[1, 0]) > 1e-06)
        or (min(matrix[0, 0], matrix[1, 1]) <= 0)
    ):
        raise ValueError("Opening evidence frames must have aligned axes")
    proposals = []
    diagnostics = []
    axis_masks = {}
    for segment, owners in segments.items():
        if len(owners) != 2:
            continue
        points = np.c_[np.asarray(segment, float), np.ones(2)] @ matrix.T
        points = points[:, :2] / points[:, 2:]
        axis = 0 if segment[0][1] == segment[1][1] else 1
        lo, hi = sorted(points[:, axis])
        fixed = float(points[:, 1 - axis].mean())
        scale = abs(matrix[axis, axis])
        fixed = fit_axis(ink, axis, fixed, lo, hi, stroke, scale)
        start = max(0, int(np.ceil(lo)))
        stop = min(gray.shape[1 - axis] - 1, int(np.floor(hi)))
        positions = np.arange(start, stop + 1)
        radius = max(1, round(max(stroke * 2, scale * 2)))
        key = (axis, round(scale, 6))
        if key not in axis_masks:
            length = max(3, round(max(stroke * 4, scale * POLICY["axis_support_length_units"]))) | 1
            normal_width = max(1, round(stroke)) | 1
            normal_kernel = np.ones((normal_width, 1) if axis == 0 else (1, normal_width), np.uint8)
            axis_kernel = np.ones((1, length) if axis == 0 else (length, 1), np.uint8)
            axis_masks[key] = cv2.morphologyEx(
                cv2.dilate(ink, normal_kernel), cv2.MORPH_OPEN, axis_kernel
            )
        structural = axis_masks[key]
        patch = ribbon(structural, axis, fixed, positions, radius)
        if not patch.size:
            continue
        occupied = patch.max(axis=0) > 0
        for begin, end in runs(~occupied):
            gap_lo, gap_hi = (start + begin, start + end - 1)
            width = gap_hi - gap_lo
            minimum = max(
                stroke * POLICY["minimum_gap_strokes"],
                max(gray.shape) * POLICY["minimum_gap_side_fraction"],
            )
            if width < minimum or width > max(gray.shape) * POLICY["maximum_gap_side_fraction"]:
                continue
            support_length = max(4, round(max(stroke * 6, scale * 8)))
            supports = []
            for location, direction in ((gap_lo, -1), (gap_hi, 1)):
                sample = range(
                    round(location) + direction,
                    round(location) + direction * (support_length + 1),
                    direction,
                )
                support = ribbon(structural, axis, fixed, sample, radius)
                supports.append(float(support.max(axis=0).mean()) if support.size else 0.0)
            gap_clear = float(1 - occupied[begin:end].mean())
            first = tick_evidence(
                ink,
                probabilities[3] if probabilities is not None else None,
                axis,
                fixed,
                gap_lo,
                stroke,
                scale,
            )
            second = tick_evidence(
                ink,
                probabilities[3] if probabilities is not None else None,
                axis,
                fixed,
                gap_hi,
                stroke,
                scale,
            )
            raw = min(first["raw_support"], second["raw_support"])
            semantic = min(first["model_center_response"], second["model_center_response"])
            clear_span = abs(second["position_px"] - first["position_px"])
            model_supported = (
                raw >= POLICY["raw_tick_min_support"]
                and semantic >= POLICY["model_tick_center_min"]
            )
            strong_raw = (
                mode == "paired_raw"
                and raw >= POLICY["strong_tick_min_support"]
                and (min(supports) >= POLICY["strong_wall_support_min"])
                and (gap_clear >= POLICY["strong_gap_clear_min"])
                and (gap_lo - lo >= stroke * 4)
                and (hi - gap_hi >= stroke * 4)
                and (width >= stroke * 5)
            )
            interface_patch = (
                ribbon(
                    probabilities[5], axis, fixed, range(gap_lo, gap_hi + 1), max(1, round(stroke))
                )
                if probabilities is not None
                else None
            )
            interface = (
                float(interface_patch.max(axis=0).mean())
                if interface_patch is not None and interface_patch.size
                else 0.0
            )
            record = {
                "segment": [list(p) for p in segment],
                "native_axis_px": fixed,
                "native_gap_px": [gap_lo, gap_hi],
                "raw_tick_support": raw,
                "model_center_response": semantic,
                "wall_support": supports,
                "gap_clear_fraction": gap_clear,
                "interface_response": interface,
                "ticks": [first, second],
                "mode": mode,
                "model_probability_calibrated": False,
            }
            if align_doors:
                record["paired_door_evidence"] = bool(model_supported or strong_raw)
            if (
                (model_supported or strong_raw)
                and min(supports) >= POLICY["wall_support_min"]
                and (gap_clear >= POLICY["gap_clear_min"])
                and (clear_span >= stroke * POLICY["minimum_clear_span_strokes"])
            ):
                kind = "door"
                ends = [first["position_px"], second["position_px"]]
                record["basis"] = (
                    "model_center_and_paired_ink" if model_supported else "paired_raw_geometry"
                )
            elif (
                interface >= POLICY["model_interface_min"] and gap_clear >= POLICY["gap_clear_min"]
            ):
                if align_doors and record["paired_door_evidence"]:
                    record.update(
                        status="needs_attention", reason="paired_door_evidence_unresolved"
                    )
                    diagnostics.append(record)
                    continue
                kind = "open_passage"
                ends = [gap_lo, gap_hi]
                record["basis"] = "learned_interface_and_gap"
            else:
                record["status"] = "needs_attention"
                record["reason"] = "paired_marker_or_support_incomplete"
                diagnostics.append(record)
                continue
            coordinates = sorted([(t - matrix[axis, 2]) / matrix[axis, axis] for t in ends])
            left, right = (segment[0][axis], segment[1][axis])
            if not left <= coordinates[0] < coordinates[1] <= right:
                if align_doors and kind == "door":
                    from .opening_alignment import align_interval

                    coordinates, alignment = align_interval(
                        segment, owners, coordinates, matrix, segments
                    )
                    record["alignment"] = alignment
                    if coordinates is None:
                        record.update(status="needs_attention", reason="opening_outside_support")
                        diagnostics.append(record)
                        continue
                else:
                    record.update(status="needs_attention", reason="opening_outside_support")
                    diagnostics.append(record)
                    continue
            a = list(segment[0])
            b = list(segment[1])
            a[axis], b[axis] = coordinates
            if any(
                (
                    p["segment"] == segment
                    and min(p["end"][axis], b[axis]) > max(p["start"][axis], a[axis])
                    for p in proposals
                )
            ):
                record.update(status="needs_attention", reason="opening_intervals_overlap")
                diagnostics.append(record)
                continue
            record.update(status="proposed", type=kind)
            proposals.append(
                {
                    "segment": segment,
                    "entity_indices": owners,
                    "start": a,
                    "end": b,
                    "type": kind,
                    "evidence": record,
                }
            )
            diagnostics.append(record)
    return (proposals, {"ink": ink_info, "candidates": diagnostics, "review_required": True})


def canonical_frame(
    gray, probabilities, working_gray=None, evidence_to_working=None, content_bounds=None
):
    if working_gray is None:
        scale = POLICY["canonical_side"] / max(gray.shape)
        width, height = (max(1, round(gray.shape[1] * scale)), max(1, round(gray.shape[0] * scale)))
        working_gray = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
        sx, sy = (width / gray.shape[1], height / gray.shape[0])
        evidence_to_working = np.array([[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1.0]])
    if evidence_to_working is None:
        raise ValueError("Evidence transform is required with a working image")
    matrix = np.asarray(evidence_to_working, float)
    if (
        matrix.shape != (3, 3)
        or not np.isfinite(matrix).all()
        or abs(np.linalg.det(matrix)) < 1e-12
    ):
        raise ValueError("Expected an invertible evidence transform")
    if max(working_gray.shape) > POLICY["canonical_side"]:
        raise ValueError("Region decoder frame exceeds its canonical size")
    size = (working_gray.shape[1], working_gray.shape[0])
    mapped = np.stack(
        [
            cv2.warpPerspective(
                channel,
                matrix,
                size,
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )
            for channel in probabilities
        ]
    )
    if content_bounds is not None:
        x, y, X, Y = content_bounds
        if not (0 <= x < X <= gray.shape[1] and 0 <= y < Y <= gray.shape[0]):
            raise ValueError("Content bounds must be inside the evidence image")
        support = np.zeros(gray.shape, np.uint8)
        support[y:Y, x:X] = 1
        coverage = cv2.warpPerspective(support, matrix, size, flags=cv2.INTER_NEAREST)
        mapped[:, coverage == 0] = 0
    return (working_gray, mapped, matrix)


def decode(
    gray,
    probabilities,
    source,
    metadata,
    *,
    working_gray=None,
    working_metadata=None,
    evidence_to_working=None,
    mode="paired_raw",
    region_threshold=0.5,
    region_policy="supported",
    opening_policy="legacy",
    door_policy="legacy",
    opening_alignment=False,
):
    if not np.isfinite(region_threshold) or not 0 < region_threshold < 1:
        raise ValueError("Region threshold must be between zero and one")
    working, masks, matrix = canonical_frame(
        gray,
        probabilities,
        working_gray,
        evidence_to_working,
        metadata.get("diagnostic_content_bounds_px"),
    )
    if working_metadata is None:
        forward = matrix @ np.asarray(metadata["original_to_working"])
        working_metadata = {
            **metadata,
            "working_size_px": [working.shape[1], working.shape[0]],
            "original_to_working": forward.tolist(),
            "working_to_original": np.linalg.inv(forward).tolist(),
        }
    if region_policy in ("supported", "supported-corridors"):
        from .region_recovery import region_boxes as supported_regions

        boxes, rejected, region_detail = supported_regions(
            masks,
            working,
            region_threshold,
            corridor_refinement=region_policy == "supported-corridors",
        )
    elif region_policy == "legacy":
        boxes, rejected = region_boxes(masks, working, region_threshold)
        region_detail = {"version": "legacy"}
    else:
        raise ValueError("Unknown region reconstruction policy")
    recovered_indices = []
    observed_recovery = None
    if region_policy == "supported-corridors" and opening_policy == "corridor-passages":
        from .corridor_candidates import recover
        from .corridor_junctions import project_boxes

        original_count = len(boxes)
        native_boxes = project_boxes(boxes, np.linalg.inv(matrix))
        recovered, observed_recovery = recover(gray, native_boxes, bends=True)
        from .corridor_junctions import append_manifold_regions

        boxes, canonical_rejections = append_manifold_regions(
            boxes, project_boxes(recovered[original_count:], matrix)
        )
        observed_recovery["canonical_rejections"] = canonical_rejections
        recovered_indices = list(range(original_count, len(boxes)))
        region_detail["observed_corridor_recovery"] = observed_recovery
    if opening_policy == "legacy":
        openings, evidence = opening_candidates(
            boundary_graph(boxes)[0],
            gray,
            probabilities,
            np.linalg.inv(matrix),
            mode,
            align_doors=opening_alignment,
        )
    elif opening_policy == "local-tracking" and region_policy in (
        "supported",
        "supported-corridors",
    ):
        from .local_wall_tracking import opening_candidates as tracked_openings

        openings, evidence = tracked_openings(
            boundary_graph(boxes)[0],
            gray,
            probabilities,
            np.linalg.inv(matrix),
            mode,
            align_doors=opening_alignment,
        )
    elif opening_policy == "corridor-passages" and region_policy in (
        "supported",
        "supported-corridors",
    ):
        from .passage_refinement import opening_candidates as passage_openings

        openings, evidence = passage_openings(
            boundary_graph(boxes)[0],
            gray,
            probabilities,
            np.linalg.inv(matrix),
            mode,
            region_types=[b["type"] for b in boxes],
            align_doors=opening_alignment,
        )
    else:
        raise ValueError("Unknown or incompatible opening reconstruction policy")
    if recovered_indices:
        from .corridor_junctions import add_observed_passages

        openings, physical = add_observed_passages(
            openings,
            boundary_graph(boxes)[0],
            gray,
            np.linalg.inv(matrix),
            recovered_indices,
            door_evidence=evidence if opening_alignment else None,
        )
        evidence["observed_interfaces"] = physical
    if door_policy not in ("legacy", "observed-jambs"):
        raise ValueError("Unknown door reconstruction policy")
    if door_policy == "observed-jambs" and opening_policy == "corridor-passages":
        from .door_geometry import opening_candidates as observed_doors

        openings, door_evidence = observed_doors(
            openings, boundary_graph(boxes)[0], gray, np.linalg.inv(matrix)
        )
        evidence["observed_doors"] = door_evidence
    document = authoring_document(
        source,
        working_metadata,
        boxes,
        openings,
        evidence_origin=(
            "classical" if recovered_indices or door_policy == "observed-jambs" else "model"
        ),
    )
    return (
        document,
        {
            "version": (
                "shape-decoder/2.9"
                if opening_alignment
                else (
                    "shape-decoder/2.8"
                    if door_policy == "observed-jambs" and opening_policy == "corridor-passages"
                    else (
                        "shape-decoder/2.7.1"
                        if opening_policy == "corridor-passages"
                        else (
                            "shape-decoder/2.5"
                            if opening_policy == "local-tracking"
                            else (
                                POLICY["version"]
                                if region_policy in ("supported", "supported-corridors")
                                else "shape-decoder/2.3"
                            )
                        )
                    )
                )
            ),
            "mode": mode,
            "canonical_size_px": [working.shape[1], working.shape[0]],
            "evidence_size_px": [gray.shape[1], gray.shape[0]],
            "evidence_to_working": matrix.tolist(),
            "region_rejections": rejected,
            "region_reconstruction": region_detail,
            "opening_evidence": evidence,
            "region_boxes": boxes,
            "review_required": True,
            "metric_layout_created": False,
        },
    )
