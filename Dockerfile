FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p data archive logs instance network_stub
EXPOSE 8004
CMD ["python", "run.py"]