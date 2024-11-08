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
    
    def save_status_to_log(self):
        with open('/tmp/jerb_scheduler.log', 'w') as f:
            json.dump(self.job_status, f, default=str)

    def load_status_from_log(self):
        try:
            with open('/tmp/jerb_scheduler.log', 'r') as f:
                saved_status = json.load(f)
                self.job_status.update(saved_status)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def run_job(self, job_name):
        if not self.can_run_job(job_name):
            return False
        
        job = self.jobs[job_name]
        self.job_status[job_name]['status'] = 'running'
        self.job_status[job_name]['output'] = ''
        self.save_status_to_log()
        
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
            self.job_status[job_name]['output'] = f"Command: {job['command']}\nOutput:\n{result.stdout}"
        except subprocess.CalledProcessError as e:
            self.job_status[job_name]['status'] = 'failed'
            self.job_status[job_name]['last_status'] = 'failed'
            self.job_status[job_name]['output'] = f"Command: {job['command']}\nError:\n{e.stderr}\nOutput:\n{e.stdout}"
        
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

if __name__ == '__main__':
    app.run(debug=True)
