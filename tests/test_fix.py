
import unittest
from datetime import timedelta
import redis
from rq.job import Job, JobStatus
from rq.queue import Queue
from rq_scheduler import Scheduler

class TestSchedulerRaceCondition(unittest.TestCase):
    def setUp(self):
        self.connection = redis.Redis()
        self.connection.flushall()
        self.scheduler = Scheduler(connection=self.connection)
        self.job_id = 'race_condition_job'

    def test_enqueue_in_does_not_overwrite_started_status(self):
        """
        Verify that calling enqueue_in on a job that is currently STARTED
        does not overwrite its status to SCHEDULED.
        """
        # Create a job and simulate it being STARTED (as if running)
        job = Job.create(func=lambda: None, id=self.job_id, connection=self.connection)
        job.save()
        job.set_status(JobStatus.STARTED)
        
        # Verify initial state
        job.refresh()
        self.assertEqual(job.get_status(), JobStatus.STARTED)
        
        # Schedule the same job again (simulating recursive enqueue_in from within the job)
        self.scheduler.enqueue_in(timedelta(minutes=1), lambda: None, job_id=self.job_id)
        
        # Verify that the job is in the scheduled registry (ZSET)
        self.assertIn(self.job_id, self.scheduler)
        
        # CRITICAL CHECK: Status should still be STARTED, NOT SCHEDULED
        job.refresh()
        self.assertEqual(job.get_status(), JobStatus.STARTED, 
                         "enqueue_in should not overwrite STARTED status with SCHEDULED")

    def test_enqueue_in_does_not_overwrite_queued_status(self):
        """
        Verify that calling enqueue_in on a job that is currently QUEUED
        does not overwrite its status to SCHEDULED.
        """
        # Create a job and simulate it being QUEUED
        job = Job.create(func=lambda: None, id=self.job_id, connection=self.connection)
        job.save()
        job.set_status(JobStatus.QUEUED)
        
        # Schedule the same job again
        self.scheduler.enqueue_in(timedelta(minutes=1), lambda: None, job_id=self.job_id)
        
        # Verify ZSET
        self.assertIn(self.job_id, self.scheduler)
        
        # CRITICAL CHECK
        job.refresh()
        self.assertEqual(job.get_status(), JobStatus.QUEUED,
                         "enqueue_in should not overwrite QUEUED status with SCHEDULED")

    def test_enqueue_in_updates_scheduled_status(self):
        """
        Verify that normal scheduling works (updates status if it was e.g. FINISHED or new)
        """
        # Case 1: New Job
        new_id = 'new_job'
        self.scheduler.enqueue_in(timedelta(minutes=1), lambda: None, job_id=new_id)
        job = Job.fetch(new_id, connection=self.connection)
        self.assertEqual(job.get_status(), JobStatus.SCHEDULED)
        
        # Case 2: Finished Job
        job.set_status(JobStatus.FINISHED)
        self.scheduler.enqueue_in(timedelta(minutes=1), lambda: None, job_id=new_id)
        job.refresh()
        self.assertEqual(job.get_status(), JobStatus.SCHEDULED)

if __name__ == '__main__':
    unittest.main()
