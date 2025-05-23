FROM agnohq/python:3.12

ARG USER=app
ARG APP_DIR=/app
ENV APP_DIR=${APP_DIR}

# Create user and home directory
RUN groupadd -g 61000 ${USER} \
  && useradd -g 61000 -u 61000 -ms /bin/bash -d ${APP_DIR} ${USER}

WORKDIR ${APP_DIR}

# Copy requirements.txt
COPY requirements.txt ./

# Install requirements
RUN uv pip sync requirements.txt --system

# RUN uv pip install agno==1.5.1
# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p ${APP_DIR}/db \
    && chown -R ${USER}:${USER} ${APP_DIR} \
    && chmod +x ${APP_DIR}/scripts/entrypoint.sh

# Switch to non-root user
USER ${USER}

# Expose ports for both services
EXPOSE 7777 8501

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["chill"]
