Production Deployment Guide
===========================

FastAPI Deployment Concepts
---------------------------
Deploying FastAPI in containerized environments requires an ASGI web server runner such as Uvicorn or Hypercorn.

Gunicorn Process Manager
------------------------
For multi-core scalability on Linux, combine Gunicorn process manager with Uvicorn worker classes:

.. code-block:: bash

   gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

.. note::
   When running inside container orchestration systems like Kubernetes, prefer 1 worker per container pod and scale horizontally using ReplicaSets.
