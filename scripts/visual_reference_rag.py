#!/usr/bin/env python3
"""Project-scoped visual reference catalog, retrieval, and run logging."""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError as exc:
    raise SystemExit(
        "Pillow is required. In Codex Desktop, call load_workspace_dependencies "
        "and rerun this script with the bundled Python executable."
    ) from exc


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SEMANTIC_FIELDS = (
    "description",
    "tags",
    "roles",
    "mood",
    "composition",
    "lighting",
    "texture",
    "typography",
    "subject",
)
ANNOTATION_FIELDS = {*SEMANTIC_FIELDS, "source_url", "rights", "embedding"}
FIELD_WEIGHTS = {
    "description": 2.0,
    "tags": 3.0,
    "roles": 2.5,
    "mood": 2.0,
    "composition": 2.3,
    "lighting": 2.0,
    "texture": 2.0,
    "typography": 2.3,
    "subject": 2.3,
    "path": 0.35,
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_or_absolute(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise SystemExit(f"Expected an object at {path}:{line_number}")
        records.append(item)
    return records


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n" for record in records)
    path.write_text(text, encoding="utf-8")


def project_dirs(project: Path) -> list[Path]:
    return [
        project / "references" / "raw",
        project / "references" / "selected",
        project / "catalog",
        project / "analysis" / "contact-sheets",
        project / "outputs",
        project / "runs",
    ]


def command_init(args: argparse.Namespace) -> None:
    project = Path(args.project).resolve()
    for directory in project_dirs(project):
        directory.mkdir(parents=True, exist_ok=True)
    brief = project / "brief.md"
    if not brief.exists():
        brief.write_text(
            "# Design Brief\n\n"
            "## Objective\n\n"
            "## Audience\n\n"
            "## Required content\n\n"
            "## Format and aspect ratio\n\n"
            "## Desired qualities\n\n"
            "## Avoid\n\n"
            "## Source and rights notes\n",
            encoding="utf-8",
        )
    print(json.dumps({"project": str(project), "status": "initialized"}, ensure_ascii=False))


def average_hash(image: Image.Image, size: int = 8) -> str:
    grayscale = ImageOps.grayscale(image).resize((size, size), Image.Resampling.LANCZOS)
    pixels = image_pixels(grayscale)
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
    return f"{int(bits, 2):0{size * size // 4}x}"


def hamming_hex(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()


def image_pixels(image: Image.Image) -> list[Any]:
    flattened = getattr(image, "get_flattened_data", None)
    if callable(flattened):
        return list(flattened())
    return list(image.getdata())


def image_features(path: Path) -> dict[str, Any]:
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size
        aspect_ratio = width / height if height else 0.0
        if abs(aspect_ratio - 1.0) <= 0.08:
            orientation = "square"
        elif aspect_ratio < 1.0:
            orientation = "portrait"
        else:
            orientation = "landscape"

        sample = image.copy()
        sample.thumbnail((96, 96), Image.Resampling.LANCZOS)
        pixels = image_pixels(sample)
        brightness_sum = 0.0
        saturation_sum = 0.0
        for red, green, blue in pixels:
            _, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
            brightness_sum += value
            saturation_sum += saturation
        count = max(len(pixels), 1)

        quantized = sample.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
        palette_data = quantized.getpalette() or []
        color_counts = sorted(quantized.getcolors() or [], reverse=True)
        palette: list[str] = []
        for _, palette_index in color_counts[:5]:
            offset = palette_index * 3
            if offset + 2 < len(palette_data):
                red, green, blue = palette_data[offset : offset + 3]
                palette.append(f"#{red:02X}{green:02X}{blue:02X}")

        return {
            "width": width,
            "height": height,
            "orientation": orientation,
            "aspect_ratio": round(aspect_ratio, 4),
            "palette": palette,
            "brightness": round(brightness_sum / count, 4),
            "saturation": round(saturation_sum / count, 4),
            "perceptual_hash": average_hash(image),
        }


def next_asset_number(records: Iterable[dict[str, Any]]) -> int:
    maximum = 0
    for record in records:
        match = re.fullmatch(r"img-(\d+)", str(record.get("id", "")))
        if match:
            maximum = max(maximum, int(match.group(1)))
    return maximum + 1


def make_contact_sheets(project: Path, records: list[dict[str, Any]], sheet_size: int) -> list[str]:
    output_dir = project / "analysis" / "contact-sheets"
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_sheet in output_dir.glob("sheet-*.jpg"):
        old_sheet.unlink()

    visible = [record for record in records if record.get("active", True)]
    columns = 4
    cell_width, cell_height = 300, 250
    thumb_width, thumb_height = 276, 194
    font = ImageFont.load_default()
    sheet_paths: list[str] = []

    for sheet_index, start in enumerate(range(0, len(visible), sheet_size), 1):
        batch = visible[start : start + sheet_size]
        rows = math.ceil(len(batch) / columns)
        sheet = Image.new("RGB", (columns * cell_width, max(rows, 1) * cell_height), "#F2F2F2")
        draw = ImageDraw.Draw(sheet)
        for index, record in enumerate(batch):
            row, column = divmod(index, columns)
            x, y = column * cell_width, row * cell_height
            source = project / record["path"]
            try:
                with Image.open(source) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                    thumbnail = ImageOps.contain(image, (thumb_width, thumb_height), Image.Resampling.LANCZOS)
                paste_x = x + (cell_width - thumbnail.width) // 2
                paste_y = y + 10 + (thumb_height - thumbnail.height) // 2
                sheet.paste(thumbnail, (paste_x, paste_y))
            except Exception:
                draw.rectangle((x + 12, y + 12, x + cell_width - 12, y + thumb_height), fill="#D6D6D6")
                draw.text((x + 20, y + 80), "Unreadable image", fill="#8A0000", font=font)
            filename = Path(record["path"]).name
            label = f"{record['id']}  {filename[:32]}"
            draw.text((x + 12, y + thumb_height + 20), label, fill="#111111", font=font)
            if record.get("near_duplicate_of"):
                draw.text(
                    (x + 12, y + thumb_height + 38),
                    f"near duplicate: {record['near_duplicate_of']}",
                    fill="#9A5200",
                    font=font,
                )

        sheet_path = output_dir / f"sheet-{sheet_index:03d}.jpg"
        sheet.save(sheet_path, quality=90)
        sheet_paths.append(relative_or_absolute(sheet_path, project))
    return sheet_paths


def command_catalog(args: argparse.Namespace) -> None:
    project = Path(args.project).resolve()
    raw_dir = project / "references" / "raw"
    if not raw_dir.exists():
        raise SystemExit(f"Missing {raw_dir}. Run init first.")

    catalog_path = project / "catalog" / "assets.jsonl"
    existing = load_jsonl(catalog_path)
    by_path = {str(record.get("path")): record for record in existing}
    next_number = next_asset_number(existing)
    records: list[dict[str, Any]] = []
    sha_owner: dict[str, str] = {}

    image_paths = sorted(
        path for path in raw_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    for image_path in image_paths:
        relative_path = relative_or_absolute(image_path, project)
        previous = by_path.get(relative_path, {})
        digest = sha256_file(image_path)
        asset_id = str(previous.get("id") or f"img-{next_number:04d}")
        if not previous.get("id"):
            next_number += 1

        record = dict(previous)
        old_digest = record.get("sha256")
        try:
            features = image_features(image_path)
            error = None
        except Exception as exc:
            features = {
                "width": None,
                "height": None,
                "orientation": None,
                "aspect_ratio": None,
                "palette": [],
                "brightness": None,
                "saturation": None,
                "perceptual_hash": None,
            }
            error = str(exc)

        duplicate_of = sha_owner.get(digest)
        active = duplicate_of is None and error is None
        if duplicate_of is None:
            sha_owner[digest] = asset_id

        record.update(
            {
                "id": asset_id,
                "path": relative_path,
                "sha256": digest,
                "active": active,
                "duplicate_of": duplicate_of,
                "near_duplicate_of": None,
                **features,
                "error": error,
                "needs_review": bool(old_digest and old_digest != digest),
            }
        )
        for field in SEMANTIC_FIELDS:
            if field == "description":
                record.setdefault(field, "")
            else:
                record.setdefault(field, [])
        record.setdefault("source_url", "")
        record.setdefault("rights", "unknown")
        record.setdefault("embedding", None)
        records.append(record)

    active_records = [record for record in records if record.get("active")]
    for index, record in enumerate(active_records):
        first_hash = record.get("perceptual_hash")
        first_ratio = record.get("aspect_ratio")
        if not first_hash or first_ratio is None:
            continue
        for prior in active_records[:index]:
            second_hash = prior.get("perceptual_hash")
            second_ratio = prior.get("aspect_ratio")
            if not second_hash or second_ratio is None or abs(first_ratio - second_ratio) > 0.06:
                continue
            if hamming_hex(first_hash, second_hash) <= args.near_duplicate_distance:
                record["near_duplicate_of"] = prior["id"]
                break

    records.sort(key=lambda item: item["id"])
    write_jsonl(catalog_path, records)
    sheets = make_contact_sheets(project, records, max(args.sheet_size, 1))
    summary = {
        "catalog": relative_or_absolute(catalog_path, project),
        "images": len(records),
        "active": sum(1 for record in records if record.get("active")),
        "exact_duplicates": sum(1 for record in records if record.get("duplicate_of")),
        "near_duplicates": sum(1 for record in records if record.get("near_duplicate_of")),
        "contact_sheets": sheets,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def command_annotate(args: argparse.Namespace) -> None:
    project = Path(args.project).resolve()
    catalog_path = project / "catalog" / "assets.jsonl"
    records = load_jsonl(catalog_path)
    if not records:
        raise SystemExit("No catalog records. Run catalog first.")

    annotation_path = Path(args.annotations).resolve()
    payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "annotations" in payload:
        annotations = payload["annotations"]
    elif isinstance(payload, dict):
        annotations = [{"id": asset_id, **values} for asset_id, values in payload.items()]
    else:
        annotations = payload
    if not isinstance(annotations, list):
        raise SystemExit("Annotations must be a list, an annotations object, or an id-to-fields mapping.")

    by_id = {str(record.get("id")): record for record in records}
    updated = 0
    errors: list[str] = []
    for index, annotation in enumerate(annotations, 1):
        if not isinstance(annotation, dict):
            errors.append(f"Annotation {index} is not an object.")
            continue
        asset_id = str(annotation.get("id", ""))
        if asset_id not in by_id:
            errors.append(f"Unknown asset id: {asset_id or '<missing>'}")
            continue
        unknown_fields = set(annotation) - ANNOTATION_FIELDS - {"id"}
        if unknown_fields:
            errors.append(f"{asset_id}: unsupported fields: {', '.join(sorted(unknown_fields))}")
            continue
        invalid = False
        for field in SEMANTIC_FIELDS:
            if field not in annotation:
                continue
            value = annotation[field]
            if field == "description" and not isinstance(value, str):
                errors.append(f"{asset_id}: description must be a string.")
                invalid = True
            elif field != "description" and (
                not isinstance(value, list) or not all(isinstance(item, str) for item in value)
            ):
                errors.append(f"{asset_id}: {field} must be a string array.")
                invalid = True
        embedding = annotation.get("embedding")
        if embedding is not None and (
            not isinstance(embedding, list) or not all(isinstance(value, (int, float)) for value in embedding)
        ):
            errors.append(f"{asset_id}: embedding must be null or a number array.")
            invalid = True
        if invalid:
            continue
        for field in ANNOTATION_FIELDS:
            if field in annotation:
                by_id[asset_id][field] = annotation[field]
        by_id[asset_id]["needs_review"] = False
        updated += 1

    if errors:
        raise SystemExit("Annotation validation failed:\n- " + "\n- ".join(errors))
    write_jsonl(catalog_path, sorted(records, key=lambda item: item["id"]))
    print(json.dumps({"catalog": str(catalog_path), "updated": updated}, ensure_ascii=False))


def tokenize(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]+", lowered))
    for sequence in re.findall(r"[\u3400-\u9fff]+", lowered):
        tokens.add(sequence)
        if len(sequence) > 1:
            tokens.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return {token for token in tokens if token}


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(flatten_text(item) for item in value.values())
    return str(value)


def load_taxonomy() -> dict[str, list[str]]:
    taxonomy_path = Path(__file__).resolve().parent.parent / "references" / "style-taxonomy.json"
    if not taxonomy_path.exists():
        return {}
    return json.loads(taxonomy_path.read_text(encoding="utf-8"))


def expand_query(query: str, taxonomy: dict[str, list[str]]) -> tuple[str, list[str]]:
    lowered = query.lower()
    expansions: set[str] = set()
    for key, values in taxonomy.items():
        terms = [key, *values]
        if any(term.lower() in lowered for term in terms):
            expansions.update(terms)
    expanded_terms = sorted(expansions)
    return query + " " + " ".join(expanded_terms), expanded_terms


def cosine(first: list[float], second: list[float]) -> float:
    if len(first) != len(second) or not first:
        return 0.0
    dot = sum(left * right for left, right in zip(first, second))
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if first_norm == 0 or second_norm == 0:
        return 0.0
    return dot / (first_norm * second_norm)


def load_query_embedding(path: str | None) -> list[float] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("embedding")
    if not isinstance(payload, list) or not all(isinstance(value, (int, float)) for value in payload):
        raise SystemExit("Query embedding must be a JSON number array or an object with an embedding array.")
    return [float(value) for value in payload]


def document_frequency(records: list[dict[str, Any]]) -> dict[str, int]:
    frequency: dict[str, int] = {}
    for record in records:
        combined = " ".join(flatten_text(record.get(field)) for field in (*SEMANTIC_FIELDS, "path"))
        for token in tokenize(combined):
            frequency[token] = frequency.get(token, 0) + 1
    return frequency


def visual_preference_score(query_tokens: set[str], record: dict[str, Any]) -> float:
    score = 0.0
    brightness = record.get("brightness")
    saturation = record.get("saturation")
    orientation = record.get("orientation")
    if isinstance(brightness, (int, float)):
        if query_tokens & {"暗调", "低照", "dark", "low", "夜景", "nightlife"}:
            score += 0.12 * (1.0 - brightness)
        if query_tokens & {"明亮", "bright", "airy", "高调"}:
            score += 0.12 * brightness
    if isinstance(saturation, (int, float)):
        if query_tokens & {"鲜艳", "高饱和", "vibrant", "energetic", "neon"}:
            score += 0.08 * saturation
        if query_tokens & {"低饱和", "muted", "restrained", "克制"}:
            score += 0.08 * (1.0 - saturation)
    if orientation == "portrait" and query_tokens & {"竖版", "portrait", "vertical"}:
        score += 0.12
    if orientation == "landscape" and query_tokens & {"横版", "landscape", "horizontal"}:
        score += 0.12
    if orientation == "square" and query_tokens & {"方形", "square"}:
        score += 0.12
    return score


def record_tokens(record: dict[str, Any]) -> set[str]:
    return tokenize(" ".join(flatten_text(record.get(field)) for field in SEMANTIC_FIELDS))


def record_similarity(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_embedding = first.get("embedding")
    second_embedding = second.get("embedding")
    if isinstance(first_embedding, list) and isinstance(second_embedding, list):
        embedding_similarity = max(0.0, cosine(first_embedding, second_embedding))
    else:
        embedding_similarity = 0.0
    first_tokens = record_tokens(first)
    second_tokens = record_tokens(second)
    union = first_tokens | second_tokens
    lexical = len(first_tokens & second_tokens) / len(union) if union else 0.0
    return 0.65 * lexical + 0.35 * embedding_similarity


def score_records(
    records: list[dict[str, Any]], expanded_query: str, query_embedding: list[float] | None
) -> list[dict[str, Any]]:
    query_tokens = tokenize(expanded_query)
    frequency = document_frequency(records)
    total = len(records)
    query_weight = sum(math.log((total + 1) / (frequency.get(token, 0) + 1)) + 1 for token in query_tokens)
    scored: list[dict[str, Any]] = []

    for record in records:
        field_scores: dict[str, float] = {}
        lexical_raw = 0.0
        for field, weight in FIELD_WEIGHTS.items():
            field_tokens = tokenize(flatten_text(record.get(field)))
            overlap = query_tokens & field_tokens
            value = sum(math.log((total + 1) / (frequency.get(token, 0) + 1)) + 1 for token in overlap)
            normalized = value / max(query_weight, 1.0)
            field_scores[field] = round(normalized * weight, 5)
            lexical_raw += normalized * weight
        lexical_score = min(1.0, lexical_raw / 3.2) + visual_preference_score(query_tokens, record)
        embedding_score = None
        embedding = record.get("embedding")
        if query_embedding is not None and isinstance(embedding, list):
            embedding_score = max(0.0, cosine(query_embedding, [float(value) for value in embedding]))
            relevance = 0.68 * lexical_score + 0.32 * embedding_score
        else:
            relevance = lexical_score
        scored.append(
            {
                **record,
                "_score": round(relevance, 6),
                "_score_details": {
                    "lexical_and_metadata": round(lexical_score, 6),
                    "embedding": round(embedding_score, 6) if embedding_score is not None else None,
                    "fields": field_scores,
                },
            }
        )
    return sorted(scored, key=lambda item: (-item["_score"], item["id"]))


def deduplicate_ranked(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen_groups: set[str] = set()
    output: list[dict[str, Any]] = []
    id_to_record = {record["id"]: record for record in records}
    for record in records:
        group = str(record.get("duplicate_of") or record.get("near_duplicate_of") or record["id"])
        while group in id_to_record and id_to_record[group].get("near_duplicate_of"):
            group = str(id_to_record[group]["near_duplicate_of"])
        if group in chosen_groups:
            continue
        chosen_groups.add(group)
        output.append(record)
    return output


def select_diverse(
    candidates: list[dict[str, Any]], top_k: int, requested_roles: list[str], diversity_lambda: float
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    remaining = list(candidates)
    covered_roles: set[str] = set()
    requested = set(requested_roles)

    while remaining and len(selected) < top_k:
        best: dict[str, Any] | None = None
        best_value = -float("inf")
        for candidate in remaining:
            max_similarity = max((record_similarity(candidate, item) for item in selected), default=0.0)
            candidate_roles = set(candidate.get("roles") or [])
            new_roles = requested & candidate_roles - covered_roles
            role_bonus = 0.22 * len(new_roles) / max(len(requested), 1)
            value = diversity_lambda * candidate["_score"] - (1.0 - diversity_lambda) * max_similarity + role_bonus
            if value > best_value:
                best_value = value
                best = candidate
        assert best is not None
        chosen = dict(best)
        chosen["_selection_score"] = round(best_value, 6)
        chosen["_new_role_coverage"] = sorted(requested & set(best.get("roles") or []) - covered_roles)
        selected.append(chosen)
        covered_roles.update(best.get("roles") or [])
        remaining.remove(best)
    return selected


def command_retrieve(args: argparse.Namespace) -> None:
    project = Path(args.project).resolve()
    catalog_path = project / "catalog" / "assets.jsonl"
    records = [record for record in load_jsonl(catalog_path) if record.get("active", True)]
    if not records:
        raise SystemExit("No active catalog records. Run catalog and annotate the corpus first.")

    expanded_query, expanded_terms = expand_query(args.query, load_taxonomy())
    query_embedding = load_query_embedding(args.query_embedding)
    scored = score_records(records, expanded_query, query_embedding)
    deduplicated = deduplicate_ranked(scored)
    candidates = deduplicated[: max(args.candidate_k, args.top_k)]
    roles = [role.strip() for role in args.roles.split(",") if role.strip()]
    selected = select_diverse(candidates, args.top_k, roles, args.diversity_lambda)
    covered_roles = sorted({role for record in selected for role in record.get("roles") or [] if role in roles})
    missing_roles = sorted(set(roles) - set(covered_roles))
    warnings: list[str] = []
    if len(selected) < args.top_k:
        warnings.append(f"Only {len(selected)} distinct references were available for top_k={args.top_k}.")
    if not selected or selected[0]["_score"] < args.low_score_threshold:
        warnings.append("Retrieval evidence is weak; inspect contact sheets and improve semantic annotations.")
    if missing_roles:
        warnings.append("Missing requested reference roles: " + ", ".join(missing_roles))
    if query_embedding is None:
        warnings.append("No query embedding supplied; retrieval used semantic annotations and visual metadata only.")

    def public_record(record: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if key not in {"embedding", "perceptual_hash"}}

    payload = {
        "query": args.query,
        "expanded_terms": expanded_terms,
        "configuration": {
            "active_corpus_size": len(records),
            "candidate_k": args.candidate_k,
            "top_k": args.top_k,
            "diversity_lambda": args.diversity_lambda,
            "requested_roles": roles,
            "embedding_enabled": query_embedding is not None,
        },
        "candidates": [public_record(record) for record in candidates],
        "selected": [public_record(record) for record in selected],
        "role_coverage": covered_roles,
        "warnings": warnings,
    }
    output_path = Path(args.output).resolve() if args.output else project / "analysis" / f"retrieval-{utc_stamp()}.json"
    json_dump(output_path, payload)

    if args.copy_selected:
        selected_dir = project / "references" / "selected"
        selected_dir.mkdir(parents=True, exist_ok=True)
        for old_file in selected_dir.iterdir():
            if old_file.is_file():
                old_file.unlink()
        for rank, record in enumerate(selected, 1):
            source = project / record["path"]
            destination = selected_dir / f"{rank:02d}-{record['id']}{source.suffix.lower()}"
            shutil.copy2(source, destination)

    print(json.dumps({"output": str(output_path), "selected": len(selected), "warnings": warnings}, ensure_ascii=False, indent=2))


def file_manifest(path_text: str, project: Path) -> dict[str, Any]:
    path = Path(path_text)
    if not path.is_absolute():
        path = project / path
    payload: dict[str, Any] = {"path": relative_or_absolute(path, project), "exists": path.exists()}
    if path.exists() and path.is_file():
        payload["sha256"] = sha256_file(path)
    return payload


def command_record(args: argparse.Namespace) -> None:
    project = Path(args.project).resolve()
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request": args.request,
        "style_spec": file_manifest(args.style_spec, project),
        "references": [file_manifest(path, project) for path in args.references],
        "outputs": [file_manifest(path, project) for path in args.outputs],
        "notes": args.notes or "",
    }
    output_path = project / "runs" / f"run-{utc_stamp()}.json"
    json_dump(output_path, payload)
    print(json.dumps({"output": str(output_path)}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a project directory structure.")
    init_parser.add_argument("--project", required=True)
    init_parser.set_defaults(function=command_init)

    catalog_parser = subparsers.add_parser("catalog", help="Catalog images and create contact sheets.")
    catalog_parser.add_argument("--project", required=True)
    catalog_parser.add_argument("--sheet-size", type=int, default=20)
    catalog_parser.add_argument("--near-duplicate-distance", type=int, default=5)
    catalog_parser.set_defaults(function=command_catalog)

    annotate_parser = subparsers.add_parser("annotate", help="Merge validated semantic annotations into the catalog.")
    annotate_parser.add_argument("--project", required=True)
    annotate_parser.add_argument("--annotations", required=True)
    annotate_parser.set_defaults(function=command_annotate)

    retrieve_parser = subparsers.add_parser("retrieve", help="Retrieve and diversify visual references.")
    retrieve_parser.add_argument("--project", required=True)
    retrieve_parser.add_argument("--query", required=True)
    retrieve_parser.add_argument("--top-k", type=int, default=5)
    retrieve_parser.add_argument("--candidate-k", type=int, default=20)
    retrieve_parser.add_argument("--roles", default="composition,color,typography,texture")
    retrieve_parser.add_argument("--diversity-lambda", type=float, default=0.72)
    retrieve_parser.add_argument("--low-score-threshold", type=float, default=0.08)
    retrieve_parser.add_argument("--query-embedding")
    retrieve_parser.add_argument("--output")
    retrieve_parser.add_argument("--copy-selected", action="store_true")
    retrieve_parser.set_defaults(function=command_retrieve)

    record_parser = subparsers.add_parser("record", help="Record a reproducible generation run.")
    record_parser.add_argument("--project", required=True)
    record_parser.add_argument("--request", required=True)
    record_parser.add_argument("--style-spec", required=True)
    record_parser.add_argument("--references", nargs="+", required=True)
    record_parser.add_argument("--outputs", nargs="+", required=True)
    record_parser.add_argument("--notes")
    record_parser.set_defaults(function=command_record)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "top_k") and args.top_k < 1:
        parser.error("--top-k must be positive")
    if hasattr(args, "candidate_k") and args.candidate_k < 1:
        parser.error("--candidate-k must be positive")
    if hasattr(args, "diversity_lambda") and not 0.0 <= args.diversity_lambda <= 1.0:
        parser.error("--diversity-lambda must be between 0 and 1")
    args.function(args)


if __name__ == "__main__":
    main()

