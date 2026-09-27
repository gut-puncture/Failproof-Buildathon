export function importRows(rows, { prepare, commit, concurrency }) {
  if (!Number.isInteger(concurrency) || concurrency <= 0) {
    return Promise.reject(new RangeError('concurrency must be a positive integer'));
  }

  const count = rows.length;
  if (count === 0) return Promise.resolve([]);

  return new Promise((resolve, reject) => {
    const prepared = new Array(count);
    const results = new Array(count);
    let nextToStart = 0;
    let preparing = 0;
    let preparedSettled = 0;
    let commitsStarted = 0;
    let commitsSettled = 0;
    let commitPending = false;
    let nextToCommit = 0;
    let preparationBoundary = count;
    let preparationStopped = false;
    let commitError;
    let commitFailed = false;
    let finished = false;

    const maybeFinish = () => {
      if (finished || preparedSettled + preparing !== nextToStart ||
          commitsSettled !== commitsStarted) return;
      // Every preparation that was started has either settled or is accounted
      // for by `preparing`; no more work can be started after a boundary.
      if (nextToStart < count && !preparationStopped && !commitFailed) return;
      finished = true;
      if (commitFailed) reject(commitError);
      else if (preparationBoundary < count) {
        reject(preparationFailures.get(preparationBoundary));
      } else resolve(results);
    };

    const preparationFailures = new Map();

    const startMore = () => {
      if (preparationStopped || commitFailed) return;
      while (preparing < concurrency && nextToStart < count) {
        const index = nextToStart++;
        preparing++;
        let outcome;
        try {
          // Invocation itself is synchronous; handling its outcome is not.
          outcome = Promise.resolve(prepare(rows[index], index));
        } catch (error) {
          outcome = Promise.reject(error);
        }
        outcome.then(
          value => {
            preparing--;
            preparedSettled++;
            prepared[index] = value;
            startMore();
            tryCommit();
            maybeFinish();
          },
          error => {
            preparing--;
            preparedSettled++;
            preparationFailures.set(index, error);
            if (index < preparationBoundary) preparationBoundary = index;
            preparationStopped = true;
            tryCommit();
            maybeFinish();
          }
        );
      }
    };

    const tryCommit = () => {
      if (commitPending || commitFailed || nextToCommit >= count ||
          nextToCommit >= preparationBoundary ||
          !Object.prototype.hasOwnProperty.call(prepared, nextToCommit)) {
        maybeFinish();
        return;
      }

      const index = nextToCommit++;
      commitsStarted++;
      commitPending = true;
      let outcome;
      try {
        outcome = Promise.resolve(commit(prepared[index], index));
      } catch (error) {
        outcome = Promise.reject(error);
      }
      outcome.then(
        value => {
          results[index] = value;
          commitPending = false;
          commitsSettled++;
          tryCommit();
          maybeFinish();
        },
        error => {
          commitPending = false;
          commitsSettled++;
          commitError = error;
          commitFailed = true;
          preparationStopped = true;
          maybeFinish();
        }
      );
    };

    // This is deliberately synchronous: the first batch of callbacks starts
    // before importRows returns, even when those callbacks return values.
    startMore();
  });
}
