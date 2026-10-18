/** Python indexes Unicode code points; browser selections index UTF-16 units. */
export function selectionOffsets(text: string, startUtf16: number, endUtf16: number) {
  if (startUtf16 < 0 || endUtf16 <= startUtf16 || endUtf16 > text.length) return null
  const start = Array.from(text.slice(0, startUtf16)).length
  const end = Array.from(text.slice(0, endUtf16)).length
  const selected = text.slice(startUtf16, endUtf16)
  if (Array.from(text).slice(start, end).join('') !== selected) return null
  return { start, end, selected }
}

/** Textareas normalize CRLF to LF; map their offsets back to the source first. */
export function textareaSelectionOffsets(text: string, start: number, end: number) {
  const sourceBoundaries = [0]
  let index = 0
  while (index < text.length) {
    index += text[index] === '\r' && text[index + 1] === '\n' ? 2 : 1
    sourceBoundaries.push(index)
  }
  if (start < 0 || end >= sourceBoundaries.length) return null
  return selectionOffsets(text, sourceBoundaries[start], sourceBoundaries[end])
}

/** Read a selection only when both ends belong to this exact source message. */
export function readSourceSelection(container: HTMLElement, text: string) {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null
  const range = selection.getRangeAt(0)
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null
  const before = range.cloneRange()
  before.selectNodeContents(container)
  before.setEnd(range.startContainer, range.startOffset)
  const start = before.toString().length
  return selectionOffsets(text, start, start + range.toString().length)
}
