# Deployment overview

The project is designed for straightforward deployment in a container-based environment. The root Docker Compose file brings up the backend and frontend services together, while the individual Dockerfiles allow each part of the stack to be built independently.

For local development, a simple environment file and a single Compose command are enough to start the system. For a production deployment, the same structure can be adapted to a managed VM, a VPS, or a hosted platform that supports Docker containers.

The deployment model remains intentionally simple: the app should be easy to run and easy to understand, with configuration held outside the repository and explicit service dependencies declared in the environment.
