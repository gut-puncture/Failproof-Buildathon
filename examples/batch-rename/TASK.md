# Rename a batch of local documents safely

Implement `renameBatch(root, moves, options = {})` as a named export in `candidate.mjs`, using Node.js built-ins only. The function returns a promise. It reorganizes files in one existing folder according to moves of the form `{from: 'old.txt', to: 'new.txt'}`. Aim for under 180 source lines.

All names are direct child basenames, never paths. You may assume they are nonempty strings other than `.` and `..`, and contain no slash or backslash. File names compare exactly. Every existing child is a regular file; there are no subdirectories or symlinks initially. No other process changes the folder during the call. Files can contain arbitrary binary bytes.

Before changing anything, reject invalid plans: repeated source names, repeated destination names, missing sources, or a destination already occupied by a file that is not one of the plan's sources. Do not overwrite an unrelated file. A `{from: x, to: x}` move is valid; an empty plan succeeds. Do not modify the moves array or its objects.

Treat all moves as one simultaneous renaming: swaps, cycles, and chains must work without losing or duplicating bytes. After success, each source's original contents are at its requested destination, unrelated files are unchanged, and no temporary files or directories remain. Resolve to undefined.

The operation must recover from a filesystem rename failure. `options.rename`, when supplied, replaces `node:fs/promises.rename` for EVERY rename, including staging, publishing and recovery. It has the same async `(oldPath, newPath)` signature. It may reject exactly once, before making any change for that call; all later rename calls work normally. If any rename fails, restore the entire folder to its exact original file names and contents, remove any temporary files/directories you created, and reject with that exact original Error object. Do not silently return success. You may assume other filesystem operations succeed and recovery rename calls after the one failure succeed. Use the default real fs rename when no override is supplied.

Use actual filesystem operations within root; do not modify files outside it. A temporary subdirectory within root is allowed while work is in progress. Do not change process-global state. Implement the function and verify it on disposable local files you create.
