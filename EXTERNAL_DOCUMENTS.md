# External Documents — Specification

> **Status:** normative. This is the contract for how an integration realm lands documents from an
> external store (Google Drive, Notion, Confluence, SharePoint, Dropbox, a wiki, …) in the
> assistant's searchable knowledge base, and how those documents stay fresh. The assistant side is
> **one source-neutral gateway surface**; everything source-specific — API connectivity, auth,
> content export — lives in the realm. The JVM never learns a source API.

---

## 1. The model

Document RAG over an external store has exactly three lanes. Pick per content type, not per store:

| Lane | What | When |
|---|---|---|
| **Live ops** | The realm's ordinary gateway ops (`sheets.valuesGet`, …) at query time | Volatile, operational data — a live spreadsheet, a dashboard. Ingesting these manufactures staleness. |
| **KG entities** | Virtual Cypher producers / persisted entities (see `VIRTUAL_CYPHER.md`) | Structured *records* — contacts, issues, tickets, file *metadata*. |
| **Ingested documents** | This spec | Long-form, reasonably stable *content* — docs, pages, articles, reports. Gets vector + keyword search, chunking, figures, agentic RAG. |

A store usually spans lanes: Drive file listings are KG (a `driveFiles` producer); a Google Doc's
*content* is an ingested document; a live sheet's cells are live ops.

## 2. The ingest surface (assistant-provided, source-neutral)

Two gateway methods, available to every realm handler as `ctx.ingest.*`:

### `ingest.document(args)` — land or refresh a document

```ts
ctx.ingest.document({
  content:            string,   // full text; MARKDOWN PREFERRED (headings drive chunking)
  uri:                string,   // stable source locator — see §3
  title:              string,
  sourceKind:         string,   // the store, generically: 'drive', 'notion', 'confluence', …
  sourceModifiedAt?:  string,   // the SOURCE's own version token — see §4
  ownerEmail?:        string,   // EXTERNAL owner, when the doc belongs to someone else — see §5
  publishedByDomain?: string,   // publishing org's domain, when known
})
```

Semantics the assistant guarantees:

- **Replace, never duplicate.** Re-ingesting a `uri` supersedes the stored version in the calling
  user's context. Re-running an ingest handler is therefore always safe, and is *the* refresh path.
- **Tenant isolation.** The same `uri` ingested by two users yields two isolated documents; all
  reads and the replace-delete are context-scoped.
- **Metadata stamping.** `sourceKind` and `sourceModifiedAt` are persisted on the document and
  inherited by its chunks, so both are queryable and ride into search results.

### `ingest.status(args)` — what version is held?

```ts
ctx.ingest.status({ uri: string })
// → { exists: boolean, title?: string, sourceModifiedAt?: string, ingestedAt?: string }
```

The freshness half of the protocol: a handler compares the live source's version token against
`sourceModifiedAt` and re-ingests only on drift (§4). Never errors for an unknown uri — returns
`exists: false`.

## 3. The `uri` contract

`<scheme>://<source-id>` — the scheme names the store kind, the remainder is the source's OWN
stable id:

```
drive://1AbC…            notion://space/page-uuid       confluence://12345
sharepoint://driveItemId github://owner/repo/docs/x.md  dropbox://id:abc123
```

Rules:

- **Stable across renames.** Use the store's immutable id, not a name or path that can change —
  the uri is the replace key; an unstable uri duplicates instead of refreshing.
- **Reserved schemes.** `file://`, `upload://`, `http://`, `https://` are refused — they belong to
  the assistant's built-in upload/URL ingestion paths, which do their own fetching and provenance.
  A realm that syncs content from the local filesystem still uses its own scheme (`obsidian://…`).
- One uri = one document. Split multi-document containers (a Notion database, a wiki space) into
  one ingest per page.

## 4. Freshness — the `sourceModifiedAt` anchor

`sourceModifiedAt` is the source's own version token at export time: Drive `modifiedTime`, Notion
`last_edited_time`, Confluence `version.when`, a Git commit timestamp. Any monotonic token works —
the protocol only ever compares tokens for equality/order, never interprets them.

The refresh protocol, entirely realm-side (only the realm can ask the source):

```
refresh(id):
  stored = ctx.ingest.status({ uri })
  live   = <source metadata call>            # e.g. drive.filesGet fields=modifiedTime
  if !stored.exists or live.version != stored.sourceModifiedAt:
      <export content> ; ctx.ingest.document({ …, sourceModifiedAt: live.version })
      → 'refreshed'
  else → 'fresh'
```

Expose this as a `refresh<Thing>` handler next to `ingest<Thing>`. Wire it to the realm POLL rail
(with the store's delta/changes API where one exists — Drive `changes.list`, Graph delta,
Dropbox `list_folder/continue`) for unattended freshness; the read-time answer can then also say
"as of `sourceModifiedAt`" honestly.

## 5. Attribution

- **`ownerEmail`** — set ONLY when the document genuinely belongs to someone else (shared *with*
  the user): ownership edges then point at that person instead of the ingesting user. Omit for the
  user's own content.
- **`publishedByDomain`** — the org that *published* the content (a help-center article's vendor),
  distinct from ownership. Omit when meaningless.

## 6. The handler recipe

One exported realm function per content type (see `realm-google/src/api/drive-ingest.ts` for the
reference implementation):

```ts
export async function ingestDoc(ctx: Ctx, args: { fileId: string }) {
  const meta = await ctx.drive.filesGet({ fileId, fields: "id,name,mimeType,modifiedTime,ownedByMe,owners(emailAddress)" });
  if (meta.mimeType !== GOOGLE_DOC_MIME) throw new Error(`Only Google Docs … is ${meta.mimeType}.`);  // refuse loudly — never ingest garbage
  const content = await exportMarkdown(ctx, fileId);          // markdown first, plain-text fallback
  await ctx.ingest.document({ content, uri: `drive://${meta.id}`, title: meta.name,
    sourceKind: "drive", sourceModifiedAt: meta.modifiedTime,
    ownerEmail: meta.ownedByMe === false ? meta.owners?.[0]?.emailAddress : undefined });
  return { uri: `drive://${meta.id}`, title: meta.name, sourceModifiedAt: meta.modifiedTime };
}
```

Requirements:

- **Markdown out, whatever the store speaks.** Headings become sections become chunks; a flat text
  dump chunks worse. If the store has no markdown export, assemble it (a Notion block tree, a
  sheet rendered as one `## <tab>` section + table per tab).
- **Refuse what you can't handle, by name.** A mimeType/type guard that throws "only X for now —
  '<name>' is Y" beats silently ingesting an export artifact.
- **Errors propagate.** Never catch an `ingest.document` failure into a success-shaped return —
  the caller (chat LLM, poll handler) must see failure as failure.
- **Describe for routing.** The JSDoc description is what the chat model routes on: say what kinds
  of content it ingests, that re-running refreshes, and how to find the id (e.g. via the realm's
  list/search op).
- The handler's gateway types won't include assistant built-ins — declare `ctx.ingest` as a small
  structural type (`IngestSurface` in the reference implementation).

## 7. What NOT to ingest

- **Volatile operational data** (live sheets, dashboards, queues) — use live ops; an ingested copy
  is stale the moment it lands.
- **Structured records as prose** (contact lists, issue tables) — model as KG entities/producers;
  chunked prose destroys their structure.
- **Whole stores.** Ingestion is selective and on-demand (a user asks about *this* doc) or
  poll-driven over the set already ingested. Never enumerate-and-ingest a store wholesale.
