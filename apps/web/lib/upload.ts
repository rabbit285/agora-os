import { apiFetch } from "@/lib/api";

/** Upload a file and return the id of the File row it created.
 *
 * Two steps, because the bytes never pass through the API: it hands back
 * a presigned URL and the browser PUTs straight to object storage. That
 * keeps large documents off the application server entirely.
 *
 * It also means the API cannot see the content at the moment the File
 * row is created — so the browser fingerprints it first. Without that,
 * a document has no identity but its filename, and re-uploading the same
 * policy produced a second document with its own evidence, its own
 * policy record and its own gaps. Four rows of one policy, each with a
 * different evidence count, because each run of the extractor proposed a
 * slightly different set.
 *
 * Extracted here because the same sequence was written out inline in
 * three separate pages, and a fourth copy would have been the point at
 * which one of them quietly drifted.
 */

export type UploadOutcome = {
  fileId: string;
  /** `new` — uploaded. `duplicate` — these exact bytes are already an
   * analysed document, and `fileId` is that document. `processing` — an
   * upload of them is in flight, and starting a second pipeline would
   * produce a second set of evidence for one real policy. */
  status: "new" | "duplicate" | "processing";
  message: string | null;
};

/** SHA-256 of the file, as the API expects it.
 *
 * `crypto.subtle` needs a secure context, which localhost and https both
 * are. Where it is unavailable the upload still works — the hash is a
 * hint, and the pipeline recomputes it from the real bytes — so a
 * missing digest costs an upload, never correctness.
 */
export async function fingerprint(file: File): Promise<string | undefined> {
  try {
    const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  } catch {
    return undefined;
  }
}

/** Upload, and say what happened.
 *
 * Prefer this over `uploadFile` anywhere the caller can act on the
 * answer — a document already held should send the user to it rather
 * than silently attaching a second copy.
 */
export async function uploadFileWithOutcome(
  file: File,
  options: { classification?: string } = {},
): Promise<UploadOutcome> {
  const contentType = file.type || "application/octet-stream";
  const content_hash = await fingerprint(file);

  const response = await apiFetch<{
    file_id: string;
    upload_url: string | null;
    status: "new" | "duplicate" | "processing";
    message: string | null;
  }>("/api/v1/files/upload-url", {
    method: "POST",
    body: {
      filename: file.name,
      content_type: contentType,
      size_bytes: file.size,
      classification: options.classification ?? "internal",
      ...(content_hash ? { content_hash } : {}),
    },
  });

  // Already held. There is nothing to upload and nothing to process —
  // the answer is the document the organization already has.
  if (!response.upload_url) {
    return {
      fileId: response.file_id,
      status: response.status,
      message: response.message,
    };
  }

  const putResponse = await fetch(response.upload_url, {
    method: "PUT",
    headers: { "Content-Type": contentType },
    body: file,
  });
  if (!putResponse.ok) {
    // The File row exists at this point but has no bytes behind it. Said
    // plainly rather than swallowed, because the caller is about to
    // attach it to something as evidence.
    throw new Error(
      `The document could not be uploaded to storage (status ${putResponse.status}). ` +
        "It has not been attached.",
    );
  }

  return { fileId: response.file_id, status: "new", message: null };
}

/** The id alone, for callers that only need something to attach. */
export async function uploadFile(
  file: File,
  options: { classification?: string } = {},
): Promise<string> {
  return (await uploadFileWithOutcome(file, options)).fileId;
}
