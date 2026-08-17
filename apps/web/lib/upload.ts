import { apiFetch } from "@/lib/api";

/** Upload a file and return the id of the File row it created.
 *
 * Two steps, because the bytes never pass through the API: it hands back
 * a presigned URL and the browser PUTs straight to object storage. That
 * keeps large documents off the application server entirely.
 *
 * Extracted here because the same sequence was written out inline in
 * three separate pages, and a fourth copy would have been the point at
 * which one of them quietly drifted.
 */
export async function uploadFile(
  file: File,
  options: { classification?: string } = {},
): Promise<string> {
  const contentType = file.type || "application/octet-stream";

  const { file_id, upload_url } = await apiFetch<{ file_id: string; upload_url: string }>(
    "/api/v1/files/upload-url",
    {
      method: "POST",
      body: {
        filename: file.name,
        content_type: contentType,
        size_bytes: file.size,
        classification: options.classification ?? "internal",
      },
    },
  );

  const putResponse = await fetch(upload_url, {
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

  return file_id;
}
