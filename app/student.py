from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from app.auth import role_required
from app.models import db, Class, Submission, class_students

student = Blueprint('student', __name__, url_prefix='/student')


@student.route('/dashboard')
@role_required('student')
def dashboard():
    """Student dashboard — joined classes, submissions, results."""
    joined_classes = current_user.joined_classes
    total_classes = len(joined_classes)
    total_submissions = Submission.query.filter_by(student_id=current_user.id).count()
    results_ready = Submission.query.filter(
        Submission.student_id == current_user.id,
        Submission.status != 'pending'
    ).count()

    # Get submission for each class
    class_data = []
    for cls in joined_classes:
        submission = Submission.query.filter_by(
            student_id=current_user.id, class_id=cls.id
        ).first()
        class_data.append({'class': cls, 'submission': submission})

    return render_template('student/dashboard.html',
                           class_data=class_data,
                           total_classes=total_classes,
                           total_submissions=total_submissions,
                           results_ready=results_ready)



@student.route('/join', methods=['POST'])
@role_required('student')
def join_class():
    """Join a class using a code."""
    code = request.form.get('code', '').strip().upper()
    if not code:
        flash('Please enter a class code.', 'error')
        return redirect(url_for('student.dashboard'))

    cls = Class.query.filter_by(code=code).first()
    if not cls:
        flash('Invalid class code.', 'error')
        return redirect(url_for('student.dashboard'))

    if current_user in cls.students:
        flash('You have already joined this class.', 'error')
        return redirect(url_for('student.dashboard'))

    if not cls.is_open:
        flash('This class is closed for new students.', 'error')
        return redirect(url_for('student.dashboard'))

    cls.students.append(current_user)
    db.session.commit()
    flash(f'Joined "{cls.name}" successfully!', 'success')
    return redirect(url_for('student.dashboard'))


@student.route('/upload/<string:code>', methods=['GET', 'POST'])
@role_required('student')
def upload_abstract(code):
    """Upload an abstract (PDF/DOCX) for a class."""
    import os
    from flask import current_app
    from werkzeug.utils import secure_filename

    cls = Class.query.filter_by(code=code).first_or_404()

    if current_user not in cls.students:
        flash('You are not a member of this class.', 'error')
        return redirect(url_for('student.dashboard'))

    if not cls.is_open:
        flash('Uploads are closed for this class.', 'error')
        return redirect(url_for('student.dashboard'))

    if request.method == 'POST':
        # If student already has a submission, allow re-upload (class is open)
        # Delete old submission + file + results before accepting new one
        existing = Submission.query.filter_by(
            student_id=current_user.id, class_id=cls.id
        ).first()
        if existing:
            import os as _os
            from app.models import Result
            Result.query.filter(
                (Result.submission_1_id == existing.id) | (Result.submission_2_id == existing.id)
            ).delete(synchronize_session='fetch')
            if existing.file_path and _os.path.exists(existing.file_path):
                _os.remove(existing.file_path)
            db.session.delete(existing)
            db.session.commit()
        title = request.form.get('title', '').strip()
        file = request.files.get('file')

        if not title:
            flash('Project title is required.', 'error')
            return render_template('student/upload.html', cls=cls)

        if not file or file.filename == '':
            flash('Please select a file.', 'error')
            return render_template('student/upload.html', cls=cls)

        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

        if ext not in ('pdf', 'docx'):
            flash('Only PDF and DOCX files are accepted.', 'error')
            return render_template('student/upload.html', cls=cls)

        # Save file
        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], cls.code)
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, f'{current_user.id}_{filename}')
        file.save(filepath)

        # Extract text from file
        abstract_text = extract_text(filepath, ext)
        if not abstract_text.strip():
            flash('Could not extract text from the file. Please check the document.', 'error')
            os.remove(filepath)
            return render_template('student/upload.html', cls=cls)

        submission = Submission(
            student_id=current_user.id,
            class_id=cls.id,
            project_title=title,
            abstract_text=abstract_text,
            file_path=filepath
        )
        db.session.add(submission)
        db.session.commit()
        flash('Abstract submitted successfully!', 'success')
        return redirect(url_for('student.dashboard'))

    return render_template('student/upload.html', cls=cls)


def extract_text(filepath, ext):
    """Extract text from a PDF or DOCX file."""
    try:
        if ext == 'pdf':
            from PyPDF2 import PdfReader
            reader = PdfReader(filepath)
            text = ''
            for page in reader.pages:
                text += page.extract_text() or ''
            return text
        elif ext == 'docx':
            from docx import Document
            doc = Document(filepath)
            return '\n'.join(p.text for p in doc.paragraphs)
    except Exception:
        return ''
    return ''
