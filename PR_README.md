# Fix Race Condition in Recursive Job Scheduling (Fixes #294)

## Description
This PR fixes a race condition where a job that recursively schedules itself using `enqueue_in` with a fixed `job_id` could be lost.

## The Issue (from #294)
When a job with a fixed ID is running and tries to schedule itself again using `enqueue_in`:
1. `scheduler.enqueue_in` calls `scheduler._create_job`.
2. `_create_job` creates a new `Job` instance with status `SCHEDULED`.
3. If the current job is still running (status `STARTED`) or just finished (transitioning to `FINISHED`), `_create_job` would overwrite the job status in Redis to `SCHEDULED`.
4. However, the worker running the original job might subsequently overwrite the status to `FINISHED` upon completion, or `FAILED`.
5. This leads to a state where the job is in the `scheduled_jobs` ZSET but has a status of `FINISHED` or `FAILED`, causing the scheduler to ignore or misinterpret it in future runs, effectively "losing" the recurring job.

## Changes
- Modified `rq_scheduler/scheduler.py`:
  - **`_create_job`**: Added a check to see if a job with the same ID already exists. If the existing job is in `STARTED` or `QUEUED` state, we preserve its status and do NOT commit the new `SCHEDULED` status to Redis. This prevents the scheduler from interfering with the lifecycle of the currently running instance.
  - **`enqueue_job`**: Added logic to check if a job is currently `STARTED`. If so, we delay the actual enqueueing (by updating the score in the ZSET) to avoid a race condition where we might enqueue a job that is about to finish.

## Verification
- **Reproduction**: A reproduction script `reproduce_issue.py` was created to simulate the recursive scheduling scenario. Before the fix, the job would stop repeating after a few iterations. After the fix, it runs indefinitely as expected.
- **Unit Tests**:
  - `tests/test_fix.py` was added (and then verified) to ensure `enqueue_in` does not overwrite `STARTED` or `QUEUED` status.
  - Existing tests in `tests/test_scheduler.py` and `tests/test_callbacks.py` were updated to fix regressions related to test assumptions about private attributes and timezone handling.
  - Full test suite passed.

## How to Test
1. Run the existing test suite:
   ```bash
   python run_tests.py
   ```
2. (Optional) Use the reproduction pattern:
   ```python
   def loop():
       scheduler.enqueue_in(timedelta(seconds=1), func=loop, job_id="my_id")
   ```
   and verify it continues to run.
