FROM python:3.11-slim

WORKDIR /app

RUN apt-get -y update
RUN apt-get install -y ffmpeg p7zip-full
RUN pip install --upgrade pip


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "bot.py"]
