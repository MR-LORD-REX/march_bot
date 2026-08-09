FROM python:3.11-slim-bullseye

WORKDIR /app


RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN git clone --depth=1 https://github.com/DEViantUA/StarRailCardData.git /tmp/StarRailCardData && \
    ASSETS_DIR=$(python -c "import starrailcard, os; print(os.path.join(os.path.dirname(starrailcard.__file__), 'src', 'assets'))") && \
    cp -r /tmp/StarRailCardData/asset/. "$ASSETS_DIR/" && \
    rm -rf /tmp/StarRailCardData
    
RUN pip install "numpy<2" --force-reinstall --no-cache-dir

COPY bot ./bot

COPY main.py .

EXPOSE 8000

CMD ["python", "main.py"]
