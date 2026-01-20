# Fix Race Condition in Recursive Job Scheduling

## Description
This PR addresses an issue where recursively scheduled jobs with fixed IDs could be "lost" (fail to re-execute).

### The Issue
When using `enqueue_in` to schedule a job recursively from within the job itself, using a fixed `job_id`, a race condition occurs between the Scheduler and the Worker:

1.  **Job Enqueueing:** The running job calls `enqueue_in`. This (previously) created a new Job instance and set its status to `SCHEDULED` in Redis, potentially overwriting the `STARTED` status of the currently running job.
2.  **Scheduler Processing:** The Scheduler picks up the job (status `SCHEDULED`) and moves it to the Queue (status `QUEUED`).
3.  **Job Completion:** The Worker finishes the *original* execution and updates the status to `FINISHED`, overwriting the `QUEUED` status set by the Scheduler.
4.  **Job Loss:** The next Worker picks up the job, sees status `FINISHED`, and (depending on timing/registry state) may fail to execute it or treat it as already done.

### The Fix
This PR implements a two-fold fix in `rq_scheduler/scheduler.py`:

1.  **Preserve Status in `_create_job`:** When scheduling a job that already exists (same ID), we now check its current status. If it is `STARTED` or `QUEUED`, we preserve that status instead of blindly creating it as `SCHEDULED`. This prevents the initial overwrite.
2.  **Delay Running Jobs in `enqueue_job`:** When the Scheduler attempts to move a job to the queue, it explicitly checks if the status is `STARTED`. If so, it implies the previous instance is still running (or zombie). To avoid the race condition where the Worker finishes *after* we enqueue, the Scheduler now delays the job by 1 second (updating its score in the ZSET) instead of enqueuing it immediately.

## Verification
A reproduction script was used to verify the fix.

### Steps to Reproduce / Verify
1.  Run `reproduce_issue.py` (which uses `jobs.py`).
2.  The script schedules a recursive job with a tight loop (0 delay).
3.  Observe that "Job ran!" output continues indefinitely without interruption.

## Changes
- Modified `rq_scheduler/scheduler.py`:
    - Updated `_create_job` to respect existing job status.
    - Updated `enqueue_job` to defer `STARTED` jobs.
    - Added imports (`timedelta`).
