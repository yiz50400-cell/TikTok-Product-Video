// Internal bridge runner. Customer requests are validated by package_remotion.py.
import {readFile, rm} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';

const root = path.dirname(fileURLToPath(import.meta.url));
const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Usage: node render.mjs PREPARED_DIRECTORY OUTPUT_MP4');
const inputProps = JSON.parse(await readFile(path.join(input, 'props.json'), 'utf8'));
if (inputProps.video !== 'base.mp4') throw new Error('Only the prepared local base.mp4 is accepted');
const bundleDir = path.join(path.dirname(output), 'bundle');
try {
  const serveUrl = await bundle({entryPoint: path.join(root, 'src/index.ts'),
    publicDir: path.join(input, 'media'), outDir: bundleDir});
  const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE || null;
  const composition = await selectComposition({serveUrl, id: 'ProductPackaging', inputProps, browserExecutable});
  await renderMedia({serveUrl, composition, inputProps, browserExecutable,
    codec: 'h264', pixelFormat: 'yuv420p', audioCodec: 'aac',
    colorSpace: 'bt709', imageFormat: 'png',
    muted: inputProps.audioMode === 'silent', concurrency: 2, outputLocation: output,
    crf: 18, overwrite: false});
  console.log('Rendered ProductPackaging');
} finally {
  await rm(bundleDir, {recursive: true, force: true});
}
