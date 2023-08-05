FROM python:3.11-alpine

WORKDIR /app

COPY . /app/

RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

CMD ["python3", "main.py", "--watch", "--http-logs"]
