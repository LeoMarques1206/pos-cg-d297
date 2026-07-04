import multiprocessing
import sys
import queue
import time
import uuid
import logging
from threading import Thread
from typing import Dict, Optional, Any
from pathlib import Path
from datetime import datetime

# Add parent dir to sys.path so we can import crew
sys.path.append(str(Path(__file__).parent.parent))
from crew import run as crew_run

class QueueStream:
    """Redirects stdout/stderr to a multiprocessing Queue and a Global Log file."""
    def __init__(self, q: multiprocessing.Queue, stream_type: str = "stdout"):
        self.q = q
        self.stream_type = stream_type
        
        self.log_dir = Path(__file__).parent.parent / "logs"
        self.log_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"execution_{date_str}.log"

    def write(self, msg: str):
        if msg and not msg.isspace():
            clean_msg = msg.strip()
            self.q.put({"type": "log", "stream": self.stream_type, "message": clean_msg})
            # Escrever no log global
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    f.write(f"[{timestamp}] [{self.stream_type.upper()}] {clean_msg}\n")
            except Exception:
                pass

    def flush(self):
        pass

def _pipeline_worker(job_id: str, paper_id: str, q: multiprocessing.Queue, kwargs: dict):
    """Entry point for the subprocess running the pipeline."""
    # Redirect stdout and stderr
    sys.stdout = QueueStream(q, "stdout")
    sys.stderr = QueueStream(q, "stderr")
    
    q.put({"type": "status", "status": "running"})
    try:
        from pathlib import Path
        papers_dir = Path(__file__).parent.parent / "papers"
        paper_folder = papers_dir / paper_id
        pdf_path = paper_folder / f"{paper_id}.pdf"
        
        valid_kwargs = {
            "from_step": kwargs.get("from_step"),
            "simple_mode": kwargs.get("simple_mode", False)
        }
        
        # Run the crew AI pipeline
        crew_run(pdf_path=str(pdf_path), paper_folder=paper_folder, **valid_kwargs)
        q.put({"type": "status", "status": "completed"})
    except Exception as e:
        q.put({"type": "status", "status": "failed", "error": str(e)})
        logging.exception("Pipeline failed")
    finally:
        # Restore (not strictly necessary since process dies, but good practice)
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

class PipelineJob:
    def __init__(self, paper_id: str):
        self.id = str(uuid.uuid4())
        self.paper_id = paper_id
        self.status = "queued"  # queued, running, completed, failed
        self.logs = []
        self.error: Optional[str] = None
        self.process: Optional[multiprocessing.Process] = None
        self.q = multiprocessing.Queue()
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

class PipelineManager:
    """Manages execution of pipelines via multiprocessing."""
    def __init__(self):
        self.jobs: Dict[str, PipelineJob] = {}
        self._monitor_thread = Thread(target=self._monitor_queues, daemon=True)
        self._monitor_thread.start()
        self.batch_queue = queue.Queue() # For sequential execution of batches
        self._batch_thread = Thread(target=self._process_batch_queue, daemon=True)
        self._batch_thread.start()

    def start_job(self, paper_id: str, simulate: bool = False, from_step: str = "none", simple_mode: bool = False) -> str:
        job = PipelineJob(paper_id)
        self.jobs[job.id] = job
        
        # Enqueue the job instead of starting immediately
        self.batch_queue.put((job, {
            "simulate": simulate,
            "from_step": from_step,
            "simple_mode": simple_mode,
            "max_iterations": 3
        }))
        return job.id
        
    def start_batch(self, paper_ids: list[str], simulate: bool = False, from_step: str = "none", simple_mode: bool = False) -> list[str]:
        job_ids = []
        for pid in paper_ids:
            job_ids.append(self.start_job(pid, simulate, from_step, simple_mode))
        return job_ids

    def _process_batch_queue(self):
        """Processes one job at a time."""
        while True:
            job, kwargs = self.batch_queue.get()
            job.status = "running"
            job.start_time = time.time()
            
            p = multiprocessing.Process(target=_pipeline_worker, args=(job.id, job.paper_id, job.q, kwargs))
            job.process = p
            p.start()
            p.join() # Wait for completion before starting next
            
            # Post-join cleanup handled by _monitor_queues, but we ensure status is final
            if job.status not in ["completed", "failed"]:
                job.status = "failed"
                job.error = "Process terminated unexpectedly"
                
            job.end_time = time.time()
            self.batch_queue.task_done()

    def _monitor_queues(self):
        """Polls queues for new messages from workers."""
        while True:
            for job in list(self.jobs.values()):
                if job.process:
                    try:
                        while not job.q.empty():
                            msg = job.q.get_nowait()
                            if msg["type"] == "log":
                                job.logs.append(msg["message"])
                            elif msg["type"] == "status":
                                job.status = msg["status"]
                                if "error" in msg:
                                    job.error = msg["error"]
                    except queue.Empty:
                        pass
            time.sleep(0.5)

    def get_job_status(self, job_id: str) -> dict:
        if job_id not in self.jobs:
            return {"error": "Job not found"}
            
        job = self.jobs[job_id]
        return {
            "id": job.id,
            "paper_id": job.paper_id,
            "status": job.status,
            "logs": job.logs[-100:], # Return last 100 lines for UI
            "error": job.error,
            "duration": (job.end_time or time.time()) - job.start_time if job.start_time else 0
        }
