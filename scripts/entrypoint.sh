#!/bin/bash

############################################################################
# Container Entrypoint script
############################################################################

if [[ "$PRINT_ENV_ON_LOAD" = true || "$PRINT_ENV_ON_LOAD" = True ]]; then
  echo "=================================================="
  printenv
  echo "=================================================="
fi

############################################################################
# Wait for Services
############################################################################

if [[ "$WAIT_FOR_DB" = true || "$WAIT_FOR_DB" = True ]]; then
  dockerize \
    -wait tcp://$DB_HOST:$DB_PORT \
    -timeout 300s
fi

if [[ "$WAIT_FOR_REDIS" = true || "$WAIT_FOR_REDIS" = True ]]; then
  dockerize \
    -wait tcp://$REDIS_HOST:$REDIS_PORT \
    -timeout 300s
fi

############################################################################
# Migrate database
############################################################################

if [[ "$MIGRATE_DB" = true || "$MIGRATE_DB" = True ]]; then
  echo "++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
  echo "Migrating Database"
  alembic -c db/alembic.ini upgrade head
  echo "++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
fi

############################################################################
# Start App
############################################################################

case "$1" in
  chill)
    ;;
  start)
    echo "Starting Streamlit and Playground services..."
    # Start Streamlit in the background
    streamlit run ui/pages/3_LocalToolTester.py --server.port 8501 --server.address 0.0.0.0 &
    # Start Playground
    # python playground.py
    wait # Add a wait command to prevent the script from exiting immediately
    ;;
  *)
    echo "Running: $@"
    exec "$@"
    ;;
esac

if [[ "$1" = "chill" ]]; then
  echo ">>> Hello World!"
  while true; do sleep 18000; done
fi
