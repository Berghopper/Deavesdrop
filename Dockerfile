FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get -y update
RUN apt-get install ffmpeg  -y

COPY . .

CMD ["python", "./vcrec.py"]
