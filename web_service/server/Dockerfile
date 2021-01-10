FROM python:3.8
WORKDIR /tmp
COPY server.py .
COPY requirements.txt .
RUN python -m pip install --upgrade pip
RUN python -m pip install -r requirements.txt
EXPOSE 5000
ENTRYPOINT ["python", "server.py"]
