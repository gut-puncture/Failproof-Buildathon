import {
  mkdtemp,
  readdir,
  rename as fsRename,
  rm,
} from 'node:fs/promises';
import path from 'node:path';

export async function renameBatch(root, moves, options = {}) {
  const existing = new Set(await readdir(root));
  const sources = new Set();
  const destinations = new Set();

  for (const move of moves) {
    if (sources.has(move.from)) {
      throw new Error(`repeated source name: ${move.from}`);
    }
    if (destinations.has(move.to)) {
      throw new Error(`repeated destination name: ${move.to}`);
    }
    sources.add(move.from);
    destinations.add(move.to);
  }

  for (const move of moves) {
    if (!existing.has(move.from)) {
      throw new Error(`missing source: ${move.from}`);
    }
    if (existing.has(move.to) && !sources.has(move.to)) {
      throw new Error(`destination is occupied: ${move.to}`);
    }
  }

  if (moves.length === 0) return undefined;

  const temporary = await mkdtemp(path.join(root, '.rename-batch-'));
  const rename = options.rename ?? fsRename;
  const staged = new Map();
  const published = [];

  try {
    for (let index = 0; index < moves.length; index += 1) {
      const move = moves[index];
      const source = path.join(root, move.from);
      const parked = path.join(temporary, String(index));
      await rename(source, parked);
      staged.set(move.from, parked);
    }

    for (const move of moves) {
      const parked = staged.get(move.from);
      await rename(parked, path.join(root, move.to));
      staged.delete(move.from);
      published.push(move);
    }
  } catch (error) {
    try {
      for (const move of published) {
        if (move.from !== move.to) {
          await rename(path.join(root, move.to), path.join(root, move.from));
        }
      }
      for (const [sourceName, parked] of staged) {
        await rename(parked, path.join(root, sourceName));
      }
    } catch {
      // The contract guarantees that recovery renames succeed.
    }
    throw error;
  } finally {
    try {
      await rm(temporary, { recursive: true, force: true });
    } catch {
      // Other filesystem operations are assumed to succeed.
    }
  }
}
