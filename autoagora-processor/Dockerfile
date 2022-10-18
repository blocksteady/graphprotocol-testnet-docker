FROM python:3.9 as build

ENV PYTHONUNBUFFERED=1
WORKDIR /opt/app

RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/dca6ff2699a06c0217ed6d5a278fa3146e4136ff/install-poetry.py | python -
ENV PATH=/root/.local/bin:$PATH

COPY . .

RUN poetry config virtualenvs.create false && \
    poetry env use system && \
    poetry install --no-root --no-dev -n && \
    poetry build -f wheel -n && \
    pip install dist/*.whl


FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /root

COPY --from=build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=build /usr/local/bin/autoagora-processor /usr/local/bin/autoagora-processor

CMD [ "autoagora-processor" ]
