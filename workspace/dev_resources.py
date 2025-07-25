from os import getenv

from agno.docker.app.fastapi import FastApi
from agno.docker.app.postgres import PgVectorDb
from agno.docker.app.streamlit import Streamlit
from agno.docker.resource.image import DockerImage
from agno.docker.resources import DockerResources

from workspace.settings import ws_settings

#
# -*- Resources for the Development Environment
#

# -*- Dev image
dev_image = DockerImage(
    name=f"{ws_settings.image_repo}/{ws_settings.image_name}",
    tag=ws_settings.dev_env,
    enabled=ws_settings.build_images,
    path=str(ws_settings.ws_root),
    # Do not push images after building
    push_image=ws_settings.push_images,
)

# -*- Dev database running on port 5432:5432
dev_db = PgVectorDb(
    name=f"{ws_settings.ws_name}-db",
    pg_user="ai",
    pg_password="ai",
    pg_database="ai",
    # Connect to this db on port 5432
    host_port=5432,
)

# -*- Container environment
container_env = {
    "RUNTIME_ENV": "dev",
    # Get the OpenAI API key and Exa API key from the local environment
    "OPENAI_API_KEY": getenv("OPENAI_API_KEY"),
    "EXA_API_KEY": getenv("EXA_API_KEY"),
    # Enable monitoring
    "AGNO_MONITOR": "True",
    "AGNO_API_KEY": getenv("AGNO_API_KEY"),
    # Database configuration
    "DB_HOST": dev_db.get_db_host(),
    "DB_PORT": dev_db.get_db_port(),
    "DB_USER": dev_db.get_db_user(),
    "DB_PASS": dev_db.get_db_password(),
    "DB_DATABASE": dev_db.get_db_database(),
    # Wait for database to be available before starting the application
    "WAIT_FOR_DB": dev_db.enabled,
    # Migrate database on startup using alembic
    "MIGRATE_DB": dev_db.enabled,
}

# -*- Streamlit running on port 8501:8501
dev_streamlit = Streamlit(
    name=f"{ws_settings.ws_name}-ui",
    image=dev_image,
    # Use the entrypoint script to start both Streamlit and Playground
    command="/app/scripts/entrypoint.sh start",
    # Only expose Streamlit port explicitly
    port_number=8501,
    # Attempt to expose Playground port as well
    debug_mode=True,
    mount_workspace=True,
    streamlit_server_headless=True,
    env_vars=container_env,
    use_cache=True,
    # Read secrets from secrets/dev_app_secrets.yml
    secrets_file=ws_settings.ws_root.joinpath("workspace/secrets/dev_app_secrets.yml"),
    depends_on=[dev_db],
    container_volumes={
        '/Users/fancyechocui/Downloads/mall-master': {  # Host path
            'bind': '/data/mall_code',  # Container path
            'mode': 'rw'  # Read-write access
        },
        '/Users/fancyechocui/Downloads/mall-admin-web-master': {  # Host path
            'bind': '/data/mall_admin_web',  # Containers path
            'mode': 'rw'  # Read-write access
        },
    }
)

# -*- FastAPI running on port 8000:8000
dev_fastapi = FastApi(
    name=f"{ws_settings.ws_name}-api",
    image=dev_image,
    command="uvicorn api.main:app --reload",
    port_number=8000,
    debug_mode=True,
    mount_workspace=True,
    env_vars=container_env,
    use_cache=True,
    # Read secrets from secrets/dev_app_secrets.yml
    secrets_file=ws_settings.ws_root.joinpath("workspace/secrets/dev_app_secrets.yml"),
    depends_on=[dev_db]
)

# -*- Playground running on port 7777:7777
dev_playground = FastApi(
    name=f"{ws_settings.ws_name}-playground",
    image=dev_image,
    command="uvicorn api.routes.playground:app --reload",
    port_number=7777,
    debug_mode=True,
    mount_workspace=True,
    env_vars=container_env,
    use_cache=True,
    secrets_file=ws_settings.ws_root.joinpath("workspace/secrets/dev_app_secrets.yml"),
    depends_on=[dev_db]
)

# -*- Dev DockerResources
dev_docker_resources = DockerResources(
    env=ws_settings.dev_env,
    network=ws_settings.ws_name,
    # Include db, streamlit, fastapi and playground
    apps=[dev_db, dev_streamlit, dev_fastapi, dev_playground],
)
