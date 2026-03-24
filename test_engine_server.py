"""
Standalone Similarity Engine Test Server
=========================================
Run with: python test_engine_server.py
Access at: http://localhost:5001/test

Purpose: Upload 120+ PDF/DOCX files and test the TF-IDF similarity engine.
This file is NOT part of the main application.
"""

import os
import shutil
import string
import re
from itertools import combinations
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB total
TEST_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'test_uploads_tmp')

SIMILARITY_THRESHOLD = 0.70

# ── Preprocessing ──────────────────────────────────────────────────────────────

def get_stopwords():
    try:
        from nltk.corpus import stopwords
        return set(stopwords.words('english'))
    except Exception:
        return set()

def preprocess(text):
    if not text:
        return ''
    text = text.lower()
    text = text.translate(str.maketrans('', '', string.punctuation))
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    stop = get_stopwords()
    tokens = [t for t in text.split() if t not in stop and len(t) > 2]
    return ' '.join(tokens)

# ── Text Extraction ─────────────────────────────────────────────────────────────

def extract_text(filepath, ext):
    try:
        if ext == 'pdf':
            from PyPDF2 import PdfReader
            reader = PdfReader(filepath)
            return ''.join(page.extract_text() or '' for page in reader.pages)
        elif ext == 'docx':
            from docx import Document
            doc = Document(filepath)
            return '\n'.join(p.text for p in doc.paragraphs)
    except Exception as e:
        return ''
    return ''

# ── Similarity ─────────────────────────────────────────────────────────────────

def compute_similarity(texts):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=10000, sublinear_tf=True)
    tfidf_matrix = vectorizer.fit_transform(texts)
    return cosine_similarity(tfidf_matrix)

# ── Routes ──────────────────────────────────────────────────────────────────────

@app.route('/test')
def test_page():
    return send_from_directory(os.path.dirname(__file__), 'test_similarity.html')


@app.route('/test/upload', methods=['POST'])
def upload_files():
    """Receive uploaded files, save temporarily, return file list."""
    # Clear old uploads
    if os.path.exists(TEST_UPLOAD_DIR):
        shutil.rmtree(TEST_UPLOAD_DIR)
    os.makedirs(TEST_UPLOAD_DIR)

    files = request.files.getlist('files')
    saved = []
    errors = []

    for f in files:
        if not f or not f.filename:
            continue
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext not in ('pdf', 'docx'):
            errors.append(f'{f.filename}: unsupported format (only PDF/DOCX)')
            continue
        safe_name = f.filename.replace(' ', '_')
        dest = os.path.join(TEST_UPLOAD_DIR, safe_name)
        f.save(dest)
        saved.append({'name': f.filename, 'ext': ext, 'path': dest})

    return jsonify({'uploaded': len(saved), 'errors': errors, 'files': [s['name'] for s in saved]})


@app.route('/test/run', methods=['POST'])
def run_similarity():
    """Extract text from saved files and run similarity engine."""
    try:
        if not os.path.exists(TEST_UPLOAD_DIR):
            return jsonify({'error': 'No files uploaded. Please upload files first.'}), 400

        file_entries = []
        for fname in sorted(os.listdir(TEST_UPLOAD_DIR)):
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            if ext not in ('pdf', 'docx'):
                continue
            fpath = os.path.join(TEST_UPLOAD_DIR, fname)
            text = extract_text(fpath, ext)
            processed = preprocess(text)
            file_entries.append({
                'name': fname,
                'char_count': len(text),
                'word_count': len(processed.split()),
                'processed': processed,
            })

        n = len(file_entries)
        if n < 2:
            return jsonify({'error': f'Need at least 2 valid documents with extractable text. Found {n}.'}), 400

        # Check for empty texts
        empty_docs = [e['name'] for e in file_entries if e['word_count'] == 0]
        if empty_docs:
            return jsonify({'error': f'Could not extract text from: {", ".join(empty_docs[:5])}. Ensure files contain readable text.'}), 400

        # Compute similarity matrix
        texts = [e['processed'] for e in file_entries]
        sim_matrix = compute_similarity(texts)

        # Extract pairs
        results = []
        flagged = []
        for i, j in combinations(range(n), 2):
            score = float(sim_matrix[i][j])
            pair = {
                'doc1': file_entries[i]['name'],
                'doc2': file_entries[j]['name'],
                'score': round(score * 100, 2),
                'flagged': score >= SIMILARITY_THRESHOLD,
            }
            results.append(pair)
            if score >= SIMILARITY_THRESHOLD:
                flagged.append(pair)

        # Sort flagged highest first
        results.sort(key=lambda x: x['score'], reverse=True)
        flagged.sort(key=lambda x: x['score'], reverse=True)

        return jsonify({
            'total_documents': n,
            'total_pairs': len(results),
            'flagged_count': len(flagged),
            'safe_count': len(results) - len(flagged),
            'threshold': int(SIMILARITY_THRESHOLD * 100),
            'document_stats': [
                {'name': e['name'], 'chars': e['char_count'], 'words': e['word_count']}
                for e in file_entries
            ],
            'flagged_pairs': flagged,
            'all_pairs': results[:200],  # cap output at 200 pairs for display
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Engine error: {str(e)}'}), 500


@app.route('/test/clear', methods=['POST'])
def clear_uploads():
    if os.path.exists(TEST_UPLOAD_DIR):
        shutil.rmtree(TEST_UPLOAD_DIR)
    return jsonify({'message': 'Cleared.'})


@app.errorhandler(Exception)
def handle_error(e):
    """Return JSON for any unhandled error instead of HTML."""
    return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("  Similarity Engine Test Server")
    print("  http://localhost:5001/test")
    print("=" * 50)
    app.run(port=5001, debug=False)

