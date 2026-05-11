# ── Base Image ────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# HuggingFace Spaces expects a non-root user called "user"
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR $HOME/app

# ── Dependencies ──────────────────────────────────────────────────────────────
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Application ───────────────────────────────────────────────────────────────
COPY --chown=user . .

# ── Expose & Launch ───────────────────────────────────────────────────────────
EXPOSE 7860

# Use gunicorn for production; fall back to dev server if gunicorn not available
CMD gunicorn app:server \
      --bind 0.0.0.0:7860 \
      --workers 2 \
      --timeout 120 \
      --log-level info
