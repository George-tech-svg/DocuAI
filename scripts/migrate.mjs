import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const backend = resolve(root, 'backend');
const candidates = process.platform === 'win32'
  ? [resolve(backend, '.venv', 'Scripts', 'python.exe'), 'python']
  : [resolve(backend, '.venv', 'bin', 'python'), 'python3', 'python'];
const python = candidates.find((candidate) => candidate === 'python' || candidate === 'python3' || existsSync(candidate));

if (!python) {
  console.error('Python was not found. Create backend/.venv or install Python and activate the backend environment.');
  process.exit(1);
}

const result = spawnSync(python, ['-m', 'alembic', '-c', 'alembic.ini', 'upgrade', 'head'], {
  cwd: backend,
  stdio: 'inherit',
  env: process.env,
});

if (result.error) {
  console.error(`Could not start the migration command: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
