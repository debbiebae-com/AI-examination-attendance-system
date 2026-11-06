import { mkdir, readdir, copyFile, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
const model = new URL("../public/pose/face_landmarker.task", import.meta.url);
const hash = createHash("sha256").update(await readFile(model)).digest("hex");
if (hash !== "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff") throw new Error("Face pose model missing or corrupt");
const source = new URL("../node_modules/@mediapipe/tasks-vision/wasm/", import.meta.url);
const output = new URL("../public/pose/wasm/", import.meta.url);
await mkdir(output, { recursive: true });
for (const name of await readdir(source)) {
  if (/\.(wasm|js)$/.test(name)) await copyFile(new URL(name, source), new URL(name, output));
}
