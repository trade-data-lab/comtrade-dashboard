FROM python:3.12-slim

# Hugging Face Spaces는 uid 1000 사용자로 실행한다.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    DASHBOARD_CACHE_DIR=/home/user/cache
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt \
    && python -c "import duckdb; duckdb.sql('INSTALL httpfs')"

COPY --chown=user app.py .

EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
