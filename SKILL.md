---
name: visual-reference-rag
description: Build and run project-scoped visual reference libraries for image generation. Use when Codex needs to organize a folder of poster, campaign, UI, editorial, brand, photography, or other visual references; remove duplicates; analyze style; retrieve complementary reference images; produce a grounded Style Spec; generate images from selected local references; or evaluate and record a repeatable visual-RAG run.
---

# Visual Reference RAG

Turn a changing project moodboard into a traceable image-generation workflow. Keep the reusable procedure in this skill and keep each project's references, annotations, selections, and outputs inside that project.

## Inputs

Require:

- A project directory.
- A design brief or a plain-language generation request.
- Local reference images in `references/raw/`.

Treat source URLs, rights notes, required copy, aspect ratio, and exclusions as optional but important metadata. Never modify files in `references/raw/`.

## Workflow

### 1. Initialize the project

Run:

```powershell
python scripts/visual_reference_rag.py init --project <project-directory>
```

If the default Python lacks Pillow, call the workspace dependency loader and run the script with the bundled Python it returns.

Fill `brief.md`, then place source images in `references/raw/`. Keep generated images outside the reference corpus.

### 2. Catalog and clean the corpus

Run:

```powershell
python scripts/visual_reference_rag.py catalog --project <project-directory>
```

Use the resulting contact sheets and `catalog/assets.jsonl` to review exact duplicates, near duplicates, dimensions, orientation, palette, brightness, and saturation. Do not delete source files automatically; inactive duplicate records are excluded from retrieval.

### 3. Add semantic visual annotations

Read [data-contract.md](references/data-contract.md) before editing catalog records.

- For 40 or fewer active images, inspect every image or every contact-sheet cell. This exhaustive path avoids first-stage recall loss.
- For more than 40 images, inspect contact sheets in batches, then open uncertain images individually.
- Add concise `description`, `tags`, `roles`, `mood`, `composition`, `lighting`, `texture`, `typography`, and `subject` values.
- Record what is visible. Do not infer a style from unseen images.
- Preserve existing machine-extracted fields and provenance.

Write semantic results to `analysis/annotations.json`, then merge them without editing machine-managed fields:

```powershell
python scripts/visual_reference_rag.py annotate `
  --project <project-directory> `
  --annotations <project-directory>/analysis/annotations.json
```

Use `roles` to state what each image can contribute: `composition`, `color`, `typography`, `texture`, `lighting`, `subject`, or `layout`.

### 4. Retrieve candidates and complementary references

Run:

```powershell
python scripts/visual_reference_rag.py retrieve `
  --project <project-directory> `
  --query "<design request>" `
  --top-k 5 `
  --candidate-k 20
```

The retriever expands design vocabulary, scores semantic annotations and visual metadata, excludes duplicates, then applies diversity and role coverage. If catalog records and the query contain compatible embedding vectors, it also blends cosine similarity.

Inspect the generated retrieval JSON. Select 3-5 references by default and assign an explicit contribution to each. Do not send an entire moodboard to the generator merely because it is available.

### 5. Produce a Style Spec

Read [retrieval-and-evaluation.md](references/retrieval-and-evaluation.md). Write `analysis/style-spec.json` using the schema in [data-contract.md](references/data-contract.md).

Separate:

- Content requirements: what must appear.
- Visual rules: palette, hierarchy, composition, lighting, material, typography, density, and motion cues.
- Reference roles: which image grounds which rule.
- Negative constraints: what must not be copied or generated.

Prefer transferable design principles over requests to imitate a named artist or reproduce one source image.

### 6. Generate

Pass only the selected local image paths plus the Style Spec and content brief to the available image-generation tool. Ask for materially distinct variants when exploring direction; ask for a controlled edit when refining one direction.

Do not ask the image model to render important long-form copy. Reserve stable text areas and add final typography in a layout tool when accuracy matters.

### 7. Evaluate and record

Evaluate semantic fit, style grounding, reference-role coverage, composition usability, originality, typography space, and artifact quality. Use the checklist in [retrieval-and-evaluation.md](references/retrieval-and-evaluation.md).

Save approved outputs under `outputs/`. Record each run:

```powershell
python scripts/visual_reference_rag.py record `
  --project <project-directory> `
  --request "<design request>" `
  --style-spec <style-spec-path> `
  --references <path1> <path2> <path3> `
  --outputs <output1> <output2>
```

Never add generated outputs to `references/raw/`. Add them to a separately labeled approved-output collection only when the user deliberately wants iterative self-reference.

## Retrieval Rules

- Favor recall in the candidate stage and precision in the final selection.
- Keep near duplicates out of the final set.
- Prefer complementary evidence over five images that all contribute the same thing.
- Apply hard filters for format, rights, required subject, or prohibited content before ranking.
- Surface weak evidence. If retrieval scores are low or role coverage is incomplete, inspect more references instead of pretending the selection is grounded.
- Retain the retrieval result and run manifest so the result can be reproduced and audited.

## Resources

- `scripts/visual_reference_rag.py`: initialize projects, catalog images, merge annotations, retrieve references, and record runs.
- [data-contract.md](references/data-contract.md): project layout and JSON schemas.
- [retrieval-and-evaluation.md](references/retrieval-and-evaluation.md): retrieval logic, failure handling, and evaluation guidance.
- `references/style-taxonomy.json`: compact bilingual query-expansion vocabulary used by the retriever.

