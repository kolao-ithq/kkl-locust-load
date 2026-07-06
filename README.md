Step 1: (Optional but recommended) Create a virtual environment
```
    python3 -m venv env
```
```
    source env/bin/activate
```
Step 2: Install Locust
```
    pip install locust
```

Step 3: Verify installation
```
    locust --version
```

Step 4: Run
```
    locust -f locustfile.py
```

If `env/` was created on a different machine, its `env/bin/python3` symlink may point at a Python
version that doesn't exist locally (venv errors, `pip`/`locust` not found). Fix by recreating it:
```
    rm -rf env
    python3 -m venv env
    source env/bin/activate
    pip install locust
```

## Docker

Build:
```
    docker build -t kkl-locust-load .
```

Run (web UI on http://localhost:8089):
```
    docker run --rm -p 8089:8089 kkl-locust-load
```

Run a different locustfile or pass locust flags (e.g. headless mode):
```
    docker run --rm -p 8089:8089 kkl-locust-load -f locustfile.py

    docker run --rm kkl-locust-load -f simulate.locustfile.py --headless -u 50 -r 5 --run-time 5m
```
# kkl-locust


watch -n 1 "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'"

docker service scale <service_name>=6

docker service scale \
  ithq-kkl-app-services=8 \
  ithq-kkl-sell-services=8 \
  ithq-kkl-producer-service=6 \
  ithq-kkl-core=6

  docker service scale ithq-kkl-app-services=12




locust -f locustfile.py

locust -f simulate.locustfile.py

# kkl-locust-load
