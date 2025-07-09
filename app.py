# app.py - Flask app for Demucs STEM splitting service
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import tempfile
import zipfile
import subprocess
import uuid
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)
CORS(app)  # Enable CORS for Squarespace integration

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac', 'm4a', 'aac'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>STEM Splitter API</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .upload-area { border: 2px dashed #ccc; padding: 40px; text-align: center; margin: 20px 0; }
            .upload-area:hover { border-color: #999; }
            button { background: #007cba; color: white; padding: 10px 20px; border: none; cursor: pointer; }
            button:hover { background: #005a8a; }
            .progress { display: none; margin: 20px 0; }
            .progress-bar { width: 100%; height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden; }
            .progress-fill { height: 100%; background: #007cba; width: 0%; transition: width 0.3s; }
            .result { margin: 20px 0; padding: 20px; background: #f9f9f9; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>STEM Splitter Service</h1>
        <p>Upload an audio file to split it into stems (vocals, drums, bass, other)</p>
        
        <div class="upload-area" id="uploadArea">
            <input type="file" id="fileInput" accept=".wav,.mp3,.flac,.m4a,.aac" style="display: none;">
            <p>Click to select audio file or drag and drop</p>
            <button onclick="document.getElementById('fileInput').click()">Choose File</button>
        </div>
        
        <div class="progress" id="progress">
            <p>Processing audio file...</p>
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
        </div>
        
        <div id="result" class="result" style="display: none;"></div>
        
        <script>
            const fileInput = document.getElementById('fileInput');
            const uploadArea = document.getElementById('uploadArea');
            const progress = document.getElementById('progress');
            const result = document.getElementById('result');
            
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.style.borderColor = '#007cba';
            });
            
            uploadArea.addEventListener('dragleave', (e) => {
                e.preventDefault();
                uploadArea.style.borderColor = '#ccc';
            });
            
            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.style.borderColor = '#ccc';
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    handleFile(files[0]);
                }
            });
            
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    handleFile(e.target.files[0]);
                }
            });
            
            function handleFile(file) {
                const formData = new FormData();
                formData.append('file', file);
                
                progress.style.display = 'block';
                result.style.display = 'none';
                
                fetch('/split', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    progress.style.display = 'none';
                    if (data.success) {
                        result.innerHTML = `
                            <h3>STEM splitting complete!</h3>
                            <p><a href="/download/${data.job_id}" download>Download STEM files (ZIP)</a></p>
                            <p>The ZIP file contains:</p>
                            <ul>
                                <li>vocals.wav - Isolated vocals</li>
                                <li>drums.wav - Isolated drums</li>
                                <li>bass.wav - Isolated bass</li>
                                <li>other.wav - Other instruments</li>
                            </ul>
                        `;
                        result.style.display = 'block';
                    } else {
                        result.innerHTML = `<h3>Error:</h3><p>${data.error}</p>`;
                        result.style.display = 'block';
                    }
                })
                .catch(error => {
                    progress.style.display = 'none';
                    result.innerHTML = `<h3>Error:</h3><p>${error.message}</p>`;
                    result.style.display = 'block';
                });
            }
        </script>
    </body>
    </html>
    '''

@app.route('/split', methods=['POST'])
def split_audio():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not supported'})
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        input_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{filename}")
        file.save(input_path)
        
        # Create output directory for this job
        job_output_dir = os.path.join(OUTPUT_FOLDER, job_id)
        os.makedirs(job_output_dir, exist_ok=True)
        
        # Run Demucs separation using subprocess
        try:
            # Use subprocess to run demucs
            cmd = [
                'python', '-m', 'demucs.separate',
                '--two-stems=vocals',  # This separates into vocals and no_vocals
                '--out', job_output_dir,
                input_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 minute timeout
            
            if result.returncode != 0:
                return jsonify({'success': False, 'error': f'Demucs failed: {result.stderr}'})
            
            # For full 4-stem separation, use this command instead:
            cmd_full = [
                'python', '-m', 'demucs.separate',
                '--out', job_output_dir,
                input_path
            ]
            
            result_full = subprocess.run(cmd_full, capture_output=True, text=True, timeout=300)
            
            if result_full.returncode != 0:
                return jsonify({'success': False, 'error': f'Demucs full separation failed: {result_full.stderr}'})
            
        except subprocess.TimeoutExpired:
            return jsonify({'success': False, 'error': 'Processing timeout - file may be too large'})
        except Exception as e:
            return jsonify({'success': False, 'error': f'Subprocess error: {str(e)}'})
        
        # Find the separated files
        # Demucs creates: job_output_dir/htdemucs/filename_without_ext/drums.wav, bass.wav, other.wav, vocals.wav
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        separated_dir = os.path.join(job_output_dir, 'htdemucs', base_name)
        
        if not os.path.exists(separated_dir):
            return jsonify({'success': False, 'error': f'Separation output not found at {separated_dir}'})
        
        # Create ZIP file with stems
        zip_path = os.path.join(job_output_dir, f"stems_{job_id}.zip")
        stem_files = []
        
        try:
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for file_name in os.listdir(separated_dir):
                    if file_name.endswith('.wav'):
                        file_path = os.path.join(separated_dir, file_name)
                        zipf.write(file_path, file_name)
                        stem_files.append(file_name)
            
            if not stem_files:
                return jsonify({'success': False, 'error': 'No stem files were created'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to create ZIP file: {str(e)}'})
        
        # Clean up input file
        try:
            os.remove(input_path)
        except:
            pass  # Don't fail if cleanup fails
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': 'Audio successfully split into stems',
            'stems_created': stem_files
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Unexpected error: {str(e)}'})

@app.route('/download/<job_id>')
def download_result(job_id):
    try:
        zip_path = os.path.join(OUTPUT_FOLDER, job_id, f"stems_{job_id}.zip")
        if os.path.exists(zip_path):
            return send_file(zip_path, as_attachment=True, download_name=f"stems_{job_id}.zip")
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)