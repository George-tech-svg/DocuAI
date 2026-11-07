import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const backend = resolve(root, 'backend');
const windows = process.platform === 'win32';
const activeVenvPython = process.env.VIRTUAL_ENV
  ? resolve(process.env.VIRTUAL_ENV, windows ? 'Scripts/python.exe' : 'bin/python')
  : null;
const candidates = windows
  ? [activeVenvPython, resolve(backend, '.venv311', 'Scripts', 'python.exe'), resolve(backend, '.venv', 'Scripts', 'python.exe'), 'python']
  : [activeVenvPython, resolve(backend, '.venv', 'bin', 'python'), 'python3', 'python'];
const uniqueCandidates = [...new Set(candidates.filter(Boolean))];
const usablePythons = uniqueCandidates.filter((candidate) =>
  (candidate === 'python' || candidate === 'python3' || existsSync(candidate)) &&
  spawnSync(candidate, ['-c', 'import alembic, sqlalchemy'], { cwd: backend, stdio: 'ignore', env: process.env }).status === 0
);
const python = usablePythons[0];

if (!python) {
  console.error('No usable Python environment was found. Install backend/requirements.txt in a Python environment and ensure it can import Alembic and SQLAlchemy.');
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
