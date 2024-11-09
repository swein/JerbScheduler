from flask import Flask, render_template, jsonify, request
import yaml
import subprocess
import json
import os
import socket
import threading
from datetime import datetime
import schedule
import time

app = Flask(__name__)

class JobScheduler:
    def __init__(self):
        self.jobs = {}
        self.job_status = {}
        self.load_jobs()
        self.load_status_from_log()
    
    def load_jobs(self):
        with open('jobs.yaml', 'r') as file:
            config = yaml.safe_load(file)
            self.jobs = {job['name']: job for job in config['jobs']}
            for job_name in self.jobs:
                self.job_status[job_name] = {
                    'status': 'pending',
                    'last_run': None,
                    'last_status': None
                }
    
    def can_run_job(self, job_name):
        job = self.jobs[job_name]
        for dep in job['dependencies']:
            if self.job_status[dep]['status'] == 'failed':
                return False
        return True
    
    def log_message(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open('/tmp/jerb_scheduler.log', 'a') as f:
            f.write(f"[{timestamp}] {message}\n")

    def save_status_to_log(self):
        self.log_message("Saving job status")
        with open('/tmp/jerb_scheduler_status.json', 'w') as f:
            json.dump(self.job_status, f, default=str)

    def load_status_from_log(self):
        try:
            with open('/tmp/jerb_scheduler_status.json', 'r') as f:
                saved_status = json.load(f)
                self.job_status.update(saved_status)
                self.log_message("Loaded previous job status")
        except (FileNotFoundError, json.JSONDecodeError):
            self.log_message("No previous status found or invalid status file")

    def run_job(self, job_name):
        if not self.can_run_job(job_name):
            self.log_message(f"Job {job_name} cannot run - dependencies failed")
            return False
        
        job = self.jobs[job_name]
        self.job_status[job_name]['status'] = 'running'
        self.job_status[job_name]['output'] = ''
        self.save_status_to_log()
        
        self.log_message(f"Starting job: {job_name}")
        self.log_message(f"Executing command: {job['command']}")
        
        try:
            result = subprocess.run(
                job['command'], 
                shell=True, 
                check=True,
                capture_output=True,
                text=True
            )
            self.job_status[job_name]['status'] = 'success'
            self.job_status[job_name]['last_status'] = 'success'
            output_msg = f"=== Job: {job_name} ===\nCommand: {job['command']}\nStatus: Success\nOutput:\n{result.stdout}"
            self.job_status[job_name]['output'] = output_msg
            self.log_message(output_msg)
        except subprocess.CalledProcessError as e:
            self.job_status[job_name]['status'] = 'failed'
            self.job_status[job_name]['last_status'] = 'failed'
            error_msg = f"=== Job: {job_name} ===\nCommand: {job['command']}\nStatus: Failed\nError:\n{e.stderr}\nOutput:\n{e.stdout}"
            self.job_status[job_name]['output'] = error_msg
            self.log_message(error_msg)
        
        self.job_status[job_name]['last_run'] = datetime.now()
        self.save_status_to_log()
        return True

scheduler = JobScheduler()

@app.route('/')
def index():
    hostname = socket.gethostname()
    username = os.getenv('USER', os.getenv('USERNAME', 'unknown'))
    return render_template('index.html', 
                         jobs=scheduler.jobs, 
                         status=scheduler.job_status,
                         hostname=hostname,
                         username=username)

@app.route('/api/job/<job_name>/run', methods=['POST'])
def run_job(job_name):
    if job_name in scheduler.jobs:
        success = scheduler.run_job(job_name)
        return jsonify({'success': success})
    return jsonify({'success': False, 'error': 'Job not found'})

@app.route('/api/job/<job_name>/status', methods=['GET'])
def job_status(job_name):
    if job_name in scheduler.job_status:
        return jsonify(scheduler.job_status[job_name])
    return jsonify({'error': 'Job not found'})

@app.route('/api/logs', methods=['GET'])
def get_logs():
    try:
        with open('/tmp/jerb_scheduler.log', 'r') as f:
            logs = f.read()
        return jsonify({'logs': logs})
    except FileNotFoundError:
        return jsonify({'logs': 'No logs available'})

if __name__ == '__main__':
    app.run(debug=True)
