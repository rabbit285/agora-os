import type { DocumentChunk } from "@/lib/types";

/** Putting a document back together from the pieces it was indexed as.
 *
 * Chunks are 1000-character windows that overlap by 150 so a sentence
 * cut by one boundary still survives whole in a neighbour. Rendering them
 * one after another therefore repeats a paragraph's tail at the head of
 * the next chunk — which reads as though the document stutters. The
 * overlap is found and removed here rather than shown.
 */

export type DocumentSection = {
  label: string | null;
  page: number | null;
  text: string;
};

/** The largest overlap worth looking for — chunking overlaps by 150, and
 * a longer accidental match between unrelated paragraphs would be a
 * coincidence we should not act on. */
const MAX_OVERLAP = 300;
const MIN_OVERLAP = 20;

function overlapLength(before: string, after: string): number {
  const limit = Math.min(MAX_OVERLAP, before.length, after.length);
  for (let size = limit; size >= MIN_OVERLAP; size--) {
    if (before.endsWith(after.slice(0, size))) return size;
  }
  return 0;
}

/** Group chunks into the sections the document itself declares.
 *
 * Consecutive chunks under the same heading become one block of readable
 * text. A document with no headings comes back as a single section with a
 * null label, which the viewer renders without inventing one.
 */
export function assembleSections(chunks: DocumentChunk[]): DocumentSection[] {
  const ordered = [...chunks].sort((a, b) => a.chunk_index - b.chunk_index);
  const sections: DocumentSection[] = [];

  for (const chunk of ordered) {
    const label = chunk.section_label ?? null;
    const current = sections[sections.length - 1];

    if (current && current.label === label) {
      const trimmed = overlapLength(current.text, chunk.content);
      const remainder = chunk.content.slice(trimmed);
      if (remainder.trim()) {
        current.text = `${current.text}${trimmed > 0 ? "" : "\n\n"}${remainder}`;
      }
      continue;
    }

    sections.push({
      label,
      page: chunk.page_number ?? null,
      text: chunk.content,
    });
  }

  return sections;
}

type Normalized = { text: string; offsets: number[] };

/** Collapse whitespace, remembering where each character came from.
 *
 * A citation's passage has already had its whitespace flattened by the
 * API, while the document keeps its line breaks. Matching one against the
 * other only works on a common form — and highlighting needs the original
 * offsets back, hence the map. */
function normalize(text: string): Normalized {
  const characters: string[] = [];
  const offsets: number[] = [];
  let pendingSpace = false;

  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (/\s/.test(character)) {
      pendingSpace = characters.length > 0;
      continue;
    }
    if (pendingSpace) {
      characters.push(" ");
      offsets.push(index);
      pendingSpace = false;
    }
    characters.push(character);
    offsets.push(index);
  }

  return { text: characters.join(""), offsets };
}

/** Enough of a passage to locate it without demanding an exact match. */
const ANCHOR_LENGTH = 60;

/** Where a cited passage sits in this text, as offsets into `text`.
 *
 * Returns null when the passage is not in this section, which is the
 * normal case for every section except one — the caller highlights the
 * section that answers, and leaves the rest alone rather than guessing.
 */
export function findPassage(
  text: string,
  passage: string
): { start: number; end: number } | null {
  // The ellipses are ours: `passage_from` adds them where a chunk
  // boundary cut a sentence. They are not in the document.
  const wanted = normalize(passage.replace(/…/g, " ")).text.trim();
  if (wanted.length < MIN_OVERLAP) return null;

  const haystack = normalize(text);
  let at = haystack.text.indexOf(wanted);
  let length = wanted.length;

  if (at === -1) {
    // The passage was trimmed to a sentence boundary the document does
    // not share — fall back to its opening, which is enough to put the
    // reader in the right place.
    const anchor = wanted.slice(0, ANCHOR_LENGTH);
    at = haystack.text.indexOf(anchor);
    length = anchor.length;
    if (at === -1) return null;
  }

  const start = haystack.offsets[at];
  const end = haystack.offsets[Math.min(at + length - 1, haystack.offsets.length - 1)] + 1;
  return { start, end };
}
