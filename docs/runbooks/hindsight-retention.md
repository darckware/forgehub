# Hindsight retention and Knowledge Base compaction

The Hindsight 0.8.4 instance has no document TTL. ForgeHub applies this policy through
`host-bridge/hindsight_retention.py` and `forgehub-hindsight-retention.timer`.

## Policy

- At 90 days since a document's last update, include it in the review count.
- At 180 days, archive the complete source and extracted memories as compressed JSON,
  write deduplicated active facts to a Knowledge Base Markdown note, then remove the
  original document from Hindsight. This removes the document and its memories from
  active recall. At most 100 documents are processed per daily run.
- Keep the compressed source for 60 days after archiving, then remove it. The
  Knowledge Base note remains. Manifests keep only operational metadata after purge.
- Documents tagged `retention:keep` or `retention:permanent` are exempt. Add that tag
  in the Hindsight control plane before the document reaches 180 days.

The Knowledge Base notes are drafts under `share/hindsight/compactados/`. They preserve
Hindsight's extracted facts and provenance, but may contain outdated claims. Review
and promote useful facts to the appropriate maintained note; do not treat an
automatically generated draft as an approved procedure.

Reviewed subjects live under `share/hindsight/assuntos/`, separate from compacted
drafts. A subject is removed from active Knowledge Base only when its Markdown
frontmatter explicitly says `status: descontinuado` (or `status: discontinued`).
Its compressed source remains recoverable for 60 days and is then purged. The
worker never infers discontinuation from age or an LLM response.

## Storage and recovery

- Compressed originals and manifests: `/root/backup/hindsight-retention/` (root-only).
- Knowledge Base drafts: `/root/.hermes/knowledge_base/share/hindsight/compactados/`.
- Runtime summary: `/root/backup/hindsight-retention/status.json`, surfaced on the
  Hindsight card in ForgeHub.

To inspect without deleting anything, run
`python3 host-bridge/hindsight_retention.py preview`. The scheduled service uses
`run`. Both modes list all banks and write a report; only `run` archives/deletes.

To recover an archived source within 60 days, decompress its `source.json.gz`,
take `document.original_text`, and re-retain it with the same bank and document ID
through the Hindsight API. Re-extraction may produce different memory units, so
compare the archived `memories` against the new result. Never place the compressed
source in the Knowledge Base or a public repository.

If the Knowledge Base note is missing, the purge step retains the compressed source.
If an archive or note cannot be written and read back, the source document stays in
Hindsight. Review `error_count` in the card and the service journal before retrying.
