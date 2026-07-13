# Data Contract

## Project layout

```text
project/
|-- brief.md
|-- references/
|   |-- raw/
|   `-- selected/
|-- catalog/
|   `-- assets.jsonl
|-- analysis/
|   |-- contact-sheets/
|   |-- retrieval-*.json
|   `-- style-spec.json
|-- outputs/
`-- runs/
```

## Catalog record

Each line in `catalog/assets.jsonl` is one JSON object. Machine-managed fields are preserved when semantic annotations are added.

```json
{
  "id": "img-0001",
  "path": "references/raw/example.jpg",
  "sha256": "...",
  "active": true,
  "duplicate_of": null,
  "near_duplicate_of": null,
  "width": 1080,
  "height": 1440,
  "orientation": "portrait",
  "aspect_ratio": 0.75,
  "palette": ["#1A1718", "#8F1D2C", "#D9C7A3"],
  "brightness": 0.31,
  "saturation": 0.58,
  "description": "Dark editorial poster with a central figure and narrow type.",
  "tags": ["酒馆", "编辑感", "暗红", "活动海报"],
  "roles": ["composition", "typography", "color"],
  "mood": ["intimate", "underground"],
  "composition": ["central subject", "asymmetric information"],
  "lighting": ["low key", "red practical light"],
  "texture": ["paper grain", "worn wall"],
  "typography": ["condensed sans", "large date"],
  "subject": ["person", "bar interior"],
  "source_url": "",
  "rights": "unknown",
  "embedding": null
}
```

`embedding` is optional. When present, use a normalized vector produced by one consistent image-text embedding model across the project. Do not mix vectors from different models.

## Annotation merge file

Write model-authored annotations separately so machine fields cannot be overwritten accidentally:

```json
{
  "annotations": [
    {
      "id": "img-0001",
      "description": "Dark editorial poster with a central figure.",
      "tags": ["酒馆", "编辑感", "暗红"],
      "roles": ["composition", "color"],
      "mood": ["intimate"],
      "composition": ["central subject"],
      "lighting": ["low key"],
      "texture": ["paper grain"],
      "typography": ["condensed sans"],
      "subject": ["person", "bar interior"],
      "source_url": "",
      "rights": "unknown"
    }
  ]
}
```

The `annotate` command accepts only semantic, provenance, and optional embedding fields.

## Style Spec

```json
{
  "direction_name": "Underground agent tavern",
  "content": {
    "purpose": "event recruitment poster",
    "required_elements": ["event title", "date", "venue"],
    "aspect_ratio": "3:4"
  },
  "visual_rules": {
    "palette": ["charcoal", "dark red", "warm white"],
    "composition": "central subject with reserved copy zones",
    "lighting": "low-key practical lighting",
    "texture": "subtle paper grain and worn metal",
    "typography": "condensed sans-serif with a large date",
    "density": "medium"
  },
  "reference_roles": [
    {"asset_id": "img-0001", "role": "composition"},
    {"asset_id": "img-0007", "role": "color"}
  ],
  "avoid": ["copied logos", "identifiable source characters", "illegible microtext"]
}
```

## Retrieval result

The retrieval JSON stores the original query, expanded terms, scoring configuration, ranked candidates, final selected references, role coverage, and warnings. Treat warnings as required review items before generation.

## Run manifest

Each JSON file under `runs/` records the request, Style Spec path and digest, selected references and digests, output paths, timestamp, and optional notes. This keeps iterations reproducible without contaminating the source library.

