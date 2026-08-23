import asyncio
import threading
import time
import pytest
from podqueue.core.job_runner import run_job_safely, state

@pytest.mark.asyncio
async def test_job_runner_does_not_block_default_asyncio_threadpool():
    """Verify that a long-running job in job_executor does not starve the default asyncio thread pool."""
    job_started_event = threading.Event()
    job_can_finish_event = threading.Event()
    
    def slow_job():
        job_started_event.set()
        job_can_finish_event.wait(timeout=5.0)

    job_task = asyncio.create_task(run_job_safely("Slow Job", slow_job))
    
    # Wait for the thread to signal it has started
    while not job_started_event.is_set():
        await asyncio.sleep(0.01)
        
    assert state.running is True
    assert state.current_job == "Slow Job"
    
    # Test that default asyncio.to_thread runs immediately and is NOT starved
    def quick_task():
        return "quick_result"
    
    t0 = time.perf_counter()
    result = await asyncio.to_thread(quick_task)
    t_elapsed = time.perf_counter() - t0
    
    assert result == "quick_result"
    assert t_elapsed < 0.5
    
    # Signal job to finish and wait for task
    job_can_finish_event.set()
    success = await job_task
    
    assert success is True
    assert state.running is False
    assert state.current_job is None
    assert state.last_job == "Slow Job"
    assert state.last_exit_code == 0

@pytest.mark.asyncio
async def test_concurrent_job_rejection():
    """Verify that starting a second job while one is running returns False immediately."""
    job_started = threading.Event()
    job_can_finish = threading.Event()
    
    def blocking_job():
        job_started.set()
        job_can_finish.wait(timeout=5.0)
            
    t1 = asyncio.create_task(run_job_safely("First Job", blocking_job))
    
    while not job_started.is_set():
        await asyncio.sleep(0.01)
    
    # Try running a second job while First Job is running
    second_job_result = await run_job_safely("Second Job", lambda: None)
    assert second_job_result is False
    
    job_can_finish.set()
    await t1
    assert state.running is False
    assert state.last_job == "First Job"
