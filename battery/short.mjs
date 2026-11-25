/*
 * Whether an engine answer is the whole truth, for a realm battery that reads a figure off it —
 * the JavaScript twin of short.py, which documents the three answer shapes (query, tool, view)
 * and what each field means. The two are held to the same verdicts by test_short.mjs over the
 * answers in canned/, and to the engine's own codes by engine_codes.py.
 *
 *   short(d, figure = null) -> null when whole, else "REFUSED: <why>" or
 *                              "PARTIAL <figure>: <the engine's reason>"
 *
 * Copied into realms from embabel-worlds/realm-spec (battery/) and pinned there: see
 * battery/README.md. Change it in realm-spec, not in a realm.
 */
export const SHORT_CODES = new Set([
  'PARTIAL_RESULT', 'PRODUCER_ERROR', 'NEEDS_FILTER', 'NEEDS_PRODUCER', 'FILTER_REJECTED',
  'UNPUSHED_FILTER', 'AMBIGUOUS_LABEL', 'INCOMPLETE_TRAVERSAL', 'INCOMPLETE_RANKING',
  'INCOMPLETE_AGGREGATE', 'INCOMPLETE_INPUT', 'MATERIALIZATION_FAILED', 'REDUCTION_FAILED',
  'UNPARSEABLE_ANSWER', 'TERMS_UNAVAILABLE', 'COMPUTE_FAILED', 'PROPERTY_NOT_STORED',
  'FOLLOW_CAPPED', 'UNLINKED_CHILDREN', 'RESOLUTION_DROPPED', 'AGENTIC_DEGRADED',
  'SOURCE_UNANSWERED',
])
export const SHORT_REASONS = new Set(['UNBOUNDED', 'PARTIAL_NOT_MATCHED', 'UNPUSHED_FILTER', 'DISCONNECTED',
  'INTERNAL_ERROR', 'WRITE_IN_PROGRESS', 'KILLED', 'TOO_EXPENSIVE'])
export const SHORT_PUBLIC = new Set(['PARTIAL', 'REDUCTION_FAILED', 'COMPUTE_FAILED', 'PROPERTY_NOT_STORED',
  'AGENTIC_DEGRADED', 'RATE_LIMITED', 'SOURCE_UNAVAILABLE', 'SOURCE_REJECTED', 'INVALID_FILTER',
  'UNPUSHED_FILTER', 'TOO_BROAD', 'FETCH_CAPPED', 'INDEX_UNAVAILABLE', 'ARGUMENT_REFUSED'])

export const codeOf = w => (typeof w === 'string' ? w.split(':')[0].trim() : null)

export function short(d, figure = null) {
  const tag = figure === null || figure === undefined ? 'PARTIAL' : `PARTIAL ${figure}`
  if (!d || typeof d !== 'object' || Array.isArray(d)) return `REFUSED: not an engine answer: ${String(d).slice(0, 160)}`
  if ('outcome' in d || 'status' in d) {
    if (d.status !== 'SUCCEEDED') {
      const e = d.error
      const why = e && typeof e === 'object' ? `${e.code || ''} ${e.message || ''}`.trim() : String(e ?? '')
      return `REFUSED: ${d.status} ${why.slice(0, 160)}`
    }
    const ws = (d.warnings || []).filter(w => w && typeof w === 'object' && SHORT_PUBLIC.has(w.code))
    if (!['OK', 'EMPTY'].includes(d.outcome) || ws.length) {
      const why = ws.length ? `${ws[0].code}: ${ws[0].message || ''}` : `outcome ${d.outcome}`
      return `${tag}: ${why.slice(0, 200)}`
    }
    return null
  }
  if (d.error) return `REFUSED: ${String(d.error).slice(0, 160)}`
  if (d.run) return `${tag}: the run had not finished (${JSON.stringify(d.run).slice(0, 120)})`
  const ws = (d.warnings || []).filter(w => SHORT_CODES.has(codeOf(w)))
  if (ws.length) return `${tag}: ${ws[0].slice(0, 200)}`
  if (d.incomplete) return `${tag}: ${String(d.incomplete).slice(0, 200)}`
  if (d.emptyCause === 'SOURCE_UNANSWERED') return `${tag}: emptyCause SOURCE_UNANSWERED`
  if (SHORT_REASONS.has(d.reason)) return `${tag}: reason ${d.reason}`
  if (d.answerBoundary) return `${tag}: the rows are supporting context, not an answer (answerBoundary)`
  return null
}

/* The figure in `column` of the first row of a query answer, or a view's row count. */
export function figureOf(d, column = 'n') {
  if (d && typeof d === 'object' && ('outcome' in d || 'status' in d)) return Array.isArray(d.data) ? d.data.length : 0
  const rows = (d && d.rows) || []
  return rows.length ? rows[0][column] : 0
}
