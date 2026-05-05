FROM shms/nautobot:3.1.0-py3.11

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

USER root

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

ENV PYTHONPATH="/workspace/vpn"
WORKDIR /workspace

CMD ["uvicorn", "VPN_Control_API.app:app", "--host", "0.0.0.0", "--port", "5001"]
