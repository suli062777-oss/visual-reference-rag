# Retrieval And Evaluation

## Retrieval stages

1. **Corpus validation**: exclude unreadable files, exact duplicates, inactive records, and disallowed sources.
2. **Query understanding**: expand bilingual design terms and extract requested format, subject, mood, and visual facets.
3. **High-recall candidates**: score descriptions, tags, visual facets, filenames, and optional embedding similarity. Keep more candidates than will be generated with.
4. **Constraint reranking**: apply hard requirements and penalize records missing required metadata.
5. **Diversity selection**: use maximal marginal relevance so near-identical references do not occupy every slot.
6. **Role coverage**: reward a set that jointly covers composition, color, typography, texture, lighting, subject, or layout.
7. **Context construction**: send only selected references, explicit roles, Style Spec, and negative constraints to the generator.

For a small project corpus, exhaustive visual inspection is the recall strategy. Vector retrieval is optional acceleration, not a reason to skip unreviewed references.

## Common failures

- **Low recall**: missing annotations, vocabulary mismatch, overly strict filters, or an embedding model poorly aligned with design terminology. Expand the query, inspect contact sheets, and add missing facets.
- **High recall but low precision**: broad mood tags dominate the actual task. Increase weights for purpose, subject, composition, and required format.
- **Duplicate-heavy results**: exact hashes miss crops and resizes. Use perceptual hashes and diversity penalties.
- **One-note context**: all references cover color but none cover layout or typography. Require role coverage.
- **Context dilution**: too many references create an averaged style. Reduce to 3-5 complementary images.
- **Unsupported style claim**: a Style Spec rule cannot be traced to a selected reference or the brief. Remove it or label it as a deliberate new design decision.
- **Corpus contamination**: generated images are indexed as original evidence. Keep generated outputs separate.

## Retrieval evaluation

Create 5-10 representative briefs for a reusable corpus and mark acceptable references manually.

- `Recall@candidate-k`: fraction of acceptable references appearing in the candidate set.
- `Precision@top-k`: fraction of final references judged useful.
- `Role coverage`: requested visual roles represented by the final set.
- `Duplicate rate`: redundant references in the final set.
- `Grounding coverage`: Style Spec rules traceable to the brief or selected references.

For one-off small moodboards, replace formal recall metrics with exhaustive review plus a short selection rationale.

## Generation evaluation

Score each dimension from 1-5:

- Brief and subject accuracy.
- Style grounding without direct copying.
- Composition and copy-space usability.
- Palette, lighting, texture, and typography-direction fit.
- Distinctness between exploratory variants.
- Artifact quality and small-size readability.
- Provenance and rights safety.

Reject a visually attractive result if it misses required content, has no usable copy area, reproduces source-specific logos or characters, or cannot be traced to the chosen direction.

