"""
Similarity Engine — TF-IDF + Cosine Similarity with n-gram support.
Handles up to 120+ documents efficiently.
"""

import re
import string
from itertools import combinations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Lazy-load NLTK stopwords to avoid import-time download issues
_stopwords = None


def _get_stopwords():
    """Load English stopwords from NLTK (cached after first call)."""
    global _stopwords
    if _stopwords is None:
        try:
            from nltk.corpus import stopwords
            _stopwords = set(stopwords.words('english'))
        except LookupError:
            import nltk
            nltk.download('stopwords', quiet=True)
            from nltk.corpus import stopwords
            _stopwords = set(stopwords.words('english'))
    return _stopwords


# ── Configuration ──
SIMILARITY_THRESHOLD = 0.70  # 70% — pairs at or above are flagged


def preprocess(text):
    """
    Preprocess text for comparison:
    1. Convert to lowercase
    2. Remove punctuation
    3. Remove stopwords
    4. Return cleaned text as a string
    """
    if not text:
        return ''

    # Lowercase
    text = text.lower()

    # Remove punctuation
    text = text.translate(str.maketrans('', '', string.punctuation))

    # Remove numbers
    text = re.sub(r'\d+', '', text)

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Tokenize and remove stopwords
    stop_words = _get_stopwords()
    tokens = text.split()
    tokens = [t for t in tokens if t not in stop_words and len(t) > 2]

    return ' '.join(tokens)


def compute_similarity_matrix(texts):
    """
    Build TF-IDF vectors and compute pairwise cosine similarity.
    Uses unigrams + bigrams for better accuracy.

    Args:
        texts: list of preprocessed text strings

    Returns:
        similarity matrix (numpy array, shape n×n)
    """
    if len(texts) < 2:
        return None

    # TF-IDF with unigrams + bigrams for better accuracy
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),    # unigrams + bigrams
        max_features=10000,    # cap features for speed with 120+ docs
        sublinear_tf=True,     # apply log normalization
    )

    tfidf_matrix = vectorizer.fit_transform(texts)
    sim_matrix = cosine_similarity(tfidf_matrix)

    return sim_matrix


def run_comparison(class_id):
    """
    Run the full similarity comparison pipeline for a class.

    Steps:
    1. Fetch all submissions for the class (ordered by upload time)
    2. Preprocess each abstract
    3. Compute TF-IDF + cosine similarity matrix
    4. Extract pairwise scores from upper triangle
    5. Save results to DB
    6. Update submission statuses (first = accepted, duplicate = rejected)

    Returns:
        dict with summary stats
    """
    from app.models import db, Submission, Result

    # 1. Fetch submissions ordered by upload time (first uploaded = priority)
    submissions = Submission.query.filter_by(class_id=class_id)\
        .order_by(Submission.uploaded_at.asc()).all()

    if len(submissions) < 2:
        return {'error': 'Need at least 2 submissions to compare.'}

    # Clear any previous results for this class
    Result.query.filter_by(class_id=class_id).delete()

    # Reset all statuses to 'accepted' initially
    for sub in submissions:
        sub.status = 'accepted'

    # 2. Preprocess each abstract
    texts = [preprocess(sub.abstract_text or '') for sub in submissions]

    # 3. Compute similarity matrix
    sim_matrix = compute_similarity_matrix(texts)

    if sim_matrix is None:
        return {'error': 'Could not compute similarity.'}

    # 4. Extract pairwise scores and save results
    n = len(submissions)
    total_pairs = 0
    flagged_pairs = 0
    results = []

    # Track which submissions are rejected (set of IDs)
    rejected_ids = set()

    for i, j in combinations(range(n), 2):
        score = float(sim_matrix[i][j])
        is_similar = score >= SIMILARITY_THRESHOLD

        if is_similar:
            flagged_pairs += 1
            # The later submission (j) gets rejected — i was submitted first
            # But only if i hasn't already been rejected
            if submissions[i].id not in rejected_ids:
                rejected_ids.add(submissions[j].id)
            else:
                # If i is already rejected, j still gets rejected too
                rejected_ids.add(submissions[j].id)

        total_pairs += 1

        # 5. Save result to DB
        result = Result(
            class_id=class_id,
            submission_1_id=submissions[i].id,
            submission_2_id=submissions[j].id,
            similarity_score=score,
            is_similar=is_similar
        )
        results.append(result)

    db.session.add_all(results)

    # 6. Update submission statuses
    for sub in submissions:
        if sub.id in rejected_ids:
            sub.status = 'rejected'
        else:
            sub.status = 'accepted'

    db.session.commit()

    return {
        'total_submissions': n,
        'total_pairs': total_pairs,
        'flagged_pairs': flagged_pairs,
        'safe_pairs': total_pairs - flagged_pairs,
        'threshold': SIMILARITY_THRESHOLD,
    }
