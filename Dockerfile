FROM amd64/python:3.8

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 5001

CMD ["gunicorn", "-b", "0.0.0.0:5001", "campsiteTrackerForm:app"]