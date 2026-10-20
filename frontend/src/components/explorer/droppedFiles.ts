/**
 * Turns what the browser hands over on upload -- an <input type="file">
 * selection (plain or `webkitdirectory`) or a drag-and-drop DataTransfer --
 * into a flat list of files, each carrying the path RELATIVE to the drop
 * target ("site/css/app.css"), so a whole folder is recreated on the host
 * by uploading each file to `<destination>/<relativePath>`.
 */

export interface PendingUpload {
  file: File;
  relativePath: string;
}

export function filesFromInput(list: FileList | null): PendingUpload[] {
  return Array.from(list ?? []).map((file) => ({
    file,
    // Set by <input webkitdirectory>: "folder/sub/file.txt"; "" for a plain pick.
    relativePath: file.webkitRelativePath || file.name,
  }));
}

// Minimal shapes of the (still non-standard, but universally shipped)
// FileSystem Entry API that drag-and-drop of folders relies on.
interface FsEntryLike {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  file?: (success: (file: File) => void, error?: (err: unknown) => void) => void;
  createReader?: () => { readEntries: (success: (entries: FsEntryLike[]) => void, error?: (err: unknown) => void) => void };
}

function readAllEntries(entry: FsEntryLike): Promise<FsEntryLike[]> {
  const reader = entry.createReader!();
  const all: FsEntryLike[] = [];
  // readEntries returns at most ~100 entries per call; loop until empty.
  return new Promise((resolve, reject) => {
    const next = () =>
      reader.readEntries((batch) => {
        if (batch.length === 0) resolve(all);
        else {
          all.push(...batch);
          next();
        }
      }, reject);
    next();
  });
}

async function walk(entry: FsEntryLike, prefix: string, out: PendingUpload[]): Promise<void> {
  const relativePath = prefix ? `${prefix}/${entry.name}` : entry.name;
  if (entry.isFile && entry.file) {
    const file = await new Promise<File>((resolve, reject) => entry.file!(resolve, reject));
    out.push({ file, relativePath });
  } else if (entry.isDirectory) {
    for (const child of await readAllEntries(entry)) await walk(child, relativePath, out);
  }
}

/** True when the drag carries files from the OS (vs. an internal item drag). */
export function isExternalFileDrag(dataTransfer: DataTransfer): boolean {
  return Array.from(dataTransfer.types).includes("Files");
}

export async function filesFromDataTransfer(dataTransfer: DataTransfer): Promise<PendingUpload[]> {
  // Entries must be grabbed synchronously, before the first await -- the
  // DataTransfer is emptied once the drop event handler yields.
  const entries = Array.from(dataTransfer.items)
    .filter((item) => item.kind === "file")
    .map((item) => (item as DataTransferItem & { webkitGetAsEntry?: () => FsEntryLike | null }).webkitGetAsEntry?.() ?? null);
  if (entries.length === 0 || entries.some((entry) => entry === null)) {
    return filesFromInput(dataTransfer.files);
  }
  const out: PendingUpload[] = [];
  for (const entry of entries) await walk(entry!, "", out);
  return out;
}

/** Top-level names an upload batch would create in the destination. */
export function topLevelNames(uploads: PendingUpload[]): string[] {
  return Array.from(new Set(uploads.map((u) => u.relativePath.split("/")[0])));
}
