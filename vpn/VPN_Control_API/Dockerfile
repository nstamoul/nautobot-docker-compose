FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

RUN mkdir -p /opt/vpn-control/vpn/VPN_Control_API
COPY app.py /opt/vpn-control/vpn/VPN_Control_API/app.py
COPY __init__.py /opt/vpn-control/vpn/VPN_Control_API/__init__.py

ENV PYTHONPATH="/workspace/vpn:/opt/vpn-control/vpn"
WORKDIR /workspace

CMD ["uvicorn", "VPN_Control_API.app:app", "--host", "0.0.0.0", "--port", "5001"]
